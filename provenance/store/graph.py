"""
Decision store: SQLite (temporal/relational) + ChromaDB (semantic search).

SQLite holds the full decision records with temporal metadata.
ChromaDB holds the embeddings for semantic similarity search.
Both are embedded — zero external services required.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from provenance.models import Decision


_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id           TEXT PRIMARY KEY,
    content      TEXT NOT NULL,
    why          TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    source_ref   TEXT NOT NULL,
    source_author TEXT NOT NULL,
    file_paths   TEXT NOT NULL,
    keywords     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    ingested_at  TEXT NOT NULL,
    valid_until  TEXT,
    confidence   REAL NOT NULL DEFAULT 0.8,
    repo_path    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_repo   ON decisions(repo_path);
CREATE INDEX IF NOT EXISTS idx_src    ON decisions(source_ref);
CREATE INDEX IF NOT EXISTS idx_date   ON decisions(created_at);
"""


class DecisionStore:
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            from provenance.config import get_settings
            data_dir = get_settings().data_dir

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._db = self.data_dir / "decisions.db"
        self._init_db()

        self._chroma = chromadb.PersistentClient(
            path=str(self.data_dir / "chroma")
        )
        self._col = self._chroma.get_or_create_collection(
            name="decisions",
            embedding_function=DefaultEmbeddingFunction(),
        )

    # ------------------------------------------------------------------ #
    # Write                                                                 #
    # ------------------------------------------------------------------ #

    def add(self, decision: Decision, repo_path: str = "") -> None:
        with sqlite3.connect(self._db) as con:
            con.execute(
                """INSERT OR REPLACE INTO decisions VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision.id,
                    decision.content,
                    decision.why,
                    decision.source_type,
                    decision.source_ref,
                    decision.source_author,
                    json.dumps(decision.file_paths),
                    json.dumps(decision.keywords),
                    decision.created_at.isoformat(),
                    decision.ingested_at.isoformat(),
                    decision.valid_until.isoformat() if decision.valid_until else None,
                    decision.confidence,
                    repo_path,
                ),
            )

        self._col.upsert(
            ids=[decision.id],
            documents=[f"{decision.content}\nWhy: {decision.why}"],
            metadatas=[
                {
                    "source_type": decision.source_type,
                    "source_ref": decision.source_ref,
                    "source_author": decision.source_author,
                    "created_at": decision.created_at.isoformat(),
                    "file_paths": json.dumps(decision.file_paths),
                    "repo_path": repo_path,
                }
            ],
        )

    def add_many(self, decisions: list[Decision], repo_path: str = "") -> None:
        for d in decisions:
            self.add(d, repo_path=repo_path)

    # ------------------------------------------------------------------ #
    # Read                                                                  #
    # ------------------------------------------------------------------ #

    def search(self, query: str, n_results: int = 8) -> list[Decision]:
        """Semantic similarity search."""
        total = self.count()
        if total == 0:
            return []
        results = self._col.query(
            query_texts=[query],
            n_results=min(n_results, total),
        )
        ids = results["ids"][0] if results["ids"] else []
        return self._fetch_by_ids(ids) if ids else []

    def get_by_repo(self, repo_path: str) -> list[Decision]:
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT * FROM decisions WHERE repo_path=? ORDER BY created_at DESC",
                (repo_path,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def count(self) -> int:
        with sqlite3.connect(self._db) as con:
            return con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    def all_repos(self) -> list[str]:
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT DISTINCT repo_path FROM decisions WHERE repo_path != ''"
            ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ #
    # Internal                                                              #
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        with sqlite3.connect(self._db) as con:
            con.executescript(_SCHEMA)

    def _fetch_by_ids(self, ids: list[str]) -> list[Decision]:
        placeholders = ",".join("?" * len(ids))
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                f"SELECT * FROM decisions WHERE id IN ({placeholders})", ids
            ).fetchall()
        order = {id_: i for i, id_ in enumerate(ids)}
        decisions = [self._row(r) for r in rows]
        decisions.sort(key=lambda d: order.get(d.id, 999))
        return decisions

    @staticmethod
    def _row(row: tuple) -> Decision:
        (
            id_, content, why, src_type, src_ref, src_author,
            file_paths, keywords, created_at, ingested_at,
            valid_until, confidence, _repo,
        ) = row
        return Decision(
            id=id_,
            content=content,
            why=why,
            source_type=src_type,
            source_ref=src_ref,
            source_author=src_author,
            file_paths=json.loads(file_paths),
            keywords=json.loads(keywords),
            created_at=datetime.fromisoformat(created_at),
            ingested_at=datetime.fromisoformat(ingested_at),
            valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
            confidence=float(confidence),
        )
