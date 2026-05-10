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

from anamne.models import Decision


_SCHEMA = """
-- Episodic memory: the long-term store. Every captured event/decision lives here.
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

-- Scratchpad: distilled, durable facts the user explicitly remembers.
-- Brain analog: semantic memory ("Paris is the capital of France" style).
CREATE TABLE IF NOT EXISTS scratchpad (
    id           TEXT PRIMARY KEY,
    fact         TEXT NOT NULL,
    tags         TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scratch_used ON scratchpad(last_used_at);

-- Working memory: short-lived session context. Auto-decays with TTL.
-- Brain analog: prefrontal working memory (what you're holding in your head NOW).
CREATE TABLE IF NOT EXISTS working_memory (
    id           TEXT PRIMARY KEY,
    note         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_working_exp ON working_memory(expires_at);
"""


class DecisionStore:
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            from anamne.config import get_settings
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
    # Scratchpad — durable user-provided facts                              #
    # ------------------------------------------------------------------ #

    def remember(self, fact: str, tags: Optional[list[str]] = None) -> str:
        """Add a fact to scratchpad. Returns the new memory id."""
        import uuid
        from datetime import datetime, timezone
        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db) as con:
            con.execute(
                "INSERT INTO scratchpad (id, fact, tags, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (mem_id, fact, json.dumps(tags or []), now, now),
            )
        return mem_id

    def list_facts(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT id, fact, tags, created_at, last_used_at, use_count "
                "FROM scratchpad ORDER BY last_used_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0], "fact": r[1], "tags": json.loads(r[2]),
                "created_at": r[3], "last_used_at": r[4], "use_count": r[5],
            }
            for r in rows
        ]

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        """Naive substring search over facts. Cheap, no embeddings needed."""
        q = f"%{query.lower()}%"
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT id, fact, tags FROM scratchpad "
                "WHERE LOWER(fact) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                (q, limit),
            ).fetchall()
        return [{"id": r[0], "fact": r[1], "tags": json.loads(r[2])} for r in rows]

    def forget_fact(self, mem_id: str) -> bool:
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM scratchpad WHERE id = ?", (mem_id,))
            return cur.rowcount > 0

    def touch_facts(self, mem_ids: list[str]) -> None:
        """Mark facts as used (ACT-R-style activation tracking).

        Updates last_used_at and increments use_count. Lets future ranking
        prefer facts that are recently/frequently relevant.
        """
        if not mem_ids:
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" * len(mem_ids))
        with sqlite3.connect(self._db) as con:
            con.execute(
                f"UPDATE scratchpad "
                f"SET last_used_at = ?, use_count = use_count + 1 "
                f"WHERE id IN ({placeholders})",
                [now, *mem_ids],
            )

    def fact_count(self) -> int:
        with sqlite3.connect(self._db) as con:
            return con.execute("SELECT COUNT(*) FROM scratchpad").fetchone()[0]

    # ------------------------------------------------------------------ #
    # Working memory — short-lived session context                          #
    # ------------------------------------------------------------------ #

    def working_add(self, note: str, ttl_minutes: int = 60) -> str:
        import uuid
        from datetime import datetime, timezone, timedelta
        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)
        with sqlite3.connect(self._db) as con:
            con.execute(
                "INSERT INTO working_memory (id, note, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (mem_id, note, now.isoformat(), expires.isoformat()),
            )
        return mem_id

    def working_active(self) -> list[dict]:
        """Return non-expired working-memory notes, newest first."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db) as con:
            # Drop expired entries on read (lazy GC)
            con.execute("DELETE FROM working_memory WHERE expires_at < ?", (now,))
            rows = con.execute(
                "SELECT id, note, created_at, expires_at "
                "FROM working_memory ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "note": r[1], "created_at": r[2], "expires_at": r[3]}
            for r in rows
        ]

    def working_clear(self) -> int:
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM working_memory")
            return cur.rowcount

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
