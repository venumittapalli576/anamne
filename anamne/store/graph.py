"""
Decision store: SQLite (temporal/relational) + ChromaDB (semantic search).

SQLite holds the full decision records with temporal metadata.
ChromaDB holds the embeddings for semantic similarity search on TWO collections:
  - 'decisions'  — episodic memory (git commits, ADRs)
  - 'scratchpad' — semantic search over durable facts (Phase 3 upgrade)

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

-- ACT-R retrieval log: every time a scratchpad fact is surfaced, log it.
-- Used to compute the real ACT-R activation formula:
--   A_i = ln( sum( t_j^(-d) ) )
-- where t_j = seconds since the j-th retrieval and d = decay constant (0.5).
-- More retrievals + more recent retrievals = higher activation = ranked higher.
CREATE TABLE IF NOT EXISTS retrieval_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id      TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retrieval_fact ON retrieval_log(fact_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_time ON retrieval_log(retrieved_at);

-- Incremental indexing: tracks which commits have already been processed.
-- Enables `anamne sync` to skip already-indexed commits instead of re-scanning.
CREATE TABLE IF NOT EXISTS indexed_commits (
    repo_path    TEXT NOT NULL,
    commit_hash  TEXT NOT NULL,
    indexed_at   TEXT NOT NULL,
    PRIMARY KEY (repo_path, commit_hash)
);
CREATE INDEX IF NOT EXISTS idx_commit_repo ON indexed_commits(repo_path);
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
        _ef = DefaultEmbeddingFunction()
        self._col = self._chroma.get_or_create_collection(
            name="decisions",
            embedding_function=_ef,
        )
        # Phase 3: semantic search over scratchpad facts (not just substring)
        self._scratch_col = self._chroma.get_or_create_collection(
            name="scratchpad",
            embedding_function=_ef,
        )
        self._migrate_scratchpad_to_chroma()

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

    def list_all_decisions(self, limit: int = 10_000) -> list[Decision]:
        """Return all stored decisions ordered by created_at DESC."""
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

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
        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db) as con:
            con.execute(
                "INSERT INTO scratchpad (id, fact, tags, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (mem_id, fact, json.dumps(tags or []), now, now),
            )
        # Also embed into ChromaDB for semantic search
        self._scratch_col.upsert(
            ids=[mem_id],
            documents=[fact],
            metadatas=[{"tags": json.dumps(tags or [])}],
        )
        return mem_id

    def search_facts(
        self,
        query: str,
        limit: int = 10,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        """Substring search over facts, optionally filtered by tags."""
        q = f"%{query.lower()}%"
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT id, fact, tags FROM scratchpad "
                "WHERE LOWER(fact) LIKE ? ORDER BY last_used_at DESC LIMIT ?",
                (q, limit * 3 if tags else limit),  # over-fetch when filtering
            ).fetchall()
        results = [{"id": r[0], "fact": r[1], "tags": json.loads(r[2])} for r in rows]
        if tags:
            tag_set = set(tags)
            results = [f for f in results if tag_set.intersection(f["tags"])]
        return results[:limit]

    def list_facts(self, limit: int = 50, tags: Optional[list[str]] = None) -> list[dict]:
        """List facts, optionally filtered by one or more tags."""
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT id, fact, tags, created_at, last_used_at, use_count "
                "FROM scratchpad ORDER BY last_used_at DESC LIMIT ?",
                (limit * 3 if tags else limit,),
            ).fetchall()
        results = [
            {
                "id": r[0], "fact": r[1], "tags": json.loads(r[2]),
                "created_at": r[3], "last_used_at": r[4], "use_count": r[5],
            }
            for r in rows
        ]
        if tags:
            tag_set = set(tags)
            results = [f for f in results if tag_set.intersection(f["tags"])]
        return results[:limit]

    def clear_scratchpad(self) -> int:
        """Delete all scratchpad facts. Returns count deleted."""
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM scratchpad")
            deleted = cur.rowcount
            con.execute("DELETE FROM retrieval_log")
        # Also clear ChromaDB scratchpad collection
        try:
            ids = self._scratch_col.get(include=[])["ids"]
            if ids:
                self._scratch_col.delete(ids=ids)
        except Exception:
            pass
        return deleted

    def clear_working(self) -> int:
        """Delete all working memory notes. Returns count deleted."""
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM working_memory")
            return cur.rowcount

    def clear_episodic(self) -> int:
        """Delete all episodic decisions and their embeddings."""
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM decisions")
            deleted = cur.rowcount
            con.execute("DELETE FROM indexed_commits")
        # Also clear ChromaDB decisions collection
        try:
            ids = self._col.get(include=[])["ids"]
            if ids:
                self._col.delete(ids=ids)
        except Exception:
            pass
        return deleted

    def forget_fact(self, mem_id: str) -> bool:
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM scratchpad WHERE id = ?", (mem_id,))
            deleted = cur.rowcount > 0
        if deleted:
            try:
                self._scratch_col.delete(ids=[mem_id])
            except Exception:
                pass  # ChromaDB may not have it yet (pre-migration facts)
        return deleted

    def touch_facts(self, mem_ids: list[str]) -> None:
        """Mark facts as used — updates scratchpad stats AND logs to retrieval_log.

        The retrieval_log is what makes ACT-R decay computable: every retrieval
        event is timestamped so activation_score() can apply the real formula.
        """
        if not mem_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" * len(mem_ids))
        log_rows = [(mid, now) for mid in mem_ids]
        with sqlite3.connect(self._db) as con:
            con.execute(
                f"UPDATE scratchpad "
                f"SET last_used_at = ?, use_count = use_count + 1 "
                f"WHERE id IN ({placeholders})",
                [now, *mem_ids],
            )
            con.executemany(
                "INSERT INTO retrieval_log (fact_id, retrieved_at) VALUES (?, ?)",
                log_rows,
            )

    def activation_score(self, fact_id: str, decay: float = 0.5) -> float:
        """Compute the ACT-R base-level activation for a scratchpad fact.

        Formula (Anderson & Lebiere 1998):
            A_i = ln( sum( t_j^(-d) ) )

        where t_j is the elapsed time in seconds since the j-th retrieval
        and d is the decay parameter (default 0.5 per ACT-R convention).

        A fact retrieved once five minutes ago and again just now scores
        much higher than one retrieved once a week ago — recency AND
        frequency both contribute.

        Returns 0.0 if the fact has never been retrieved.
        """
        import math
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT retrieved_at FROM retrieval_log WHERE fact_id = ?",
                (fact_id,),
            ).fetchall()

        if not rows:
            return 0.0

        total = 0.0
        for (retrieved_at,) in rows:
            t = (now - datetime.fromisoformat(retrieved_at)).total_seconds()
            if t > 0:
                total += t ** (-decay)

        return math.log(total) if total > 0 else 0.0

    def search_facts_semantic(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic (embedding-based) search over scratchpad facts.

        Slower than substring search but finds conceptually related facts even
        when exact keywords don't match. Requires ChromaDB scratchpad collection.
        Falls back to substring search if the collection is empty.
        """
        total = self.fact_count()
        if total == 0:
            return []
        try:
            results = self._scratch_col.query(
                query_texts=[query],
                n_results=min(limit, total),
            )
        except Exception:
            return self.search_facts(query, limit=limit)

        ids = results["ids"][0] if results["ids"] else []
        if not ids:
            return []

        placeholders = ",".join("?" * len(ids))
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                f"SELECT id, fact, tags FROM scratchpad WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        id_to_fact = {
            r[0]: {"id": r[0], "fact": r[1], "tags": json.loads(r[2])}
            for r in rows
        }
        return [id_to_fact[i] for i in ids if i in id_to_fact]

    def search_facts_ranked(self, query: str, limit: int = 10) -> list[dict]:
        """Hybrid search over scratchpad facts, re-ranked by ACT-R activation.

        Merges substring results + semantic results, deduplicates, then re-ranks
        by ACT-R activation score (recency × frequency). Falls back to
        last_used_at order when activation is zero (unaccessed facts).
        """
        # Merge substring + semantic candidates (over-fetch both, deduplicate)
        substring_hits = self.search_facts(query, limit=limit * 2)
        semantic_hits = self.search_facts_semantic(query, limit=limit * 2)

        seen: set[str] = set()
        merged: list[dict] = []
        for f in substring_hits + semantic_hits:
            if f["id"] not in seen:
                seen.add(f["id"])
                merged.append(f)

        if not merged:
            return []

        scored = [(self.activation_score(f["id"]), f) for f in merged]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]

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
    # Incremental indexing helpers                                          #
    # ------------------------------------------------------------------ #

    def is_commit_indexed(self, repo_path: str, commit_hash: str) -> bool:
        """Return True if this commit has already been processed."""
        with sqlite3.connect(self._db) as con:
            row = con.execute(
                "SELECT 1 FROM indexed_commits WHERE repo_path=? AND commit_hash=?",
                (repo_path, commit_hash),
            ).fetchone()
        return row is not None

    def mark_commit_indexed(self, repo_path: str, commit_hash: str) -> None:
        """Record that this commit has been processed (idempotent)."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db) as con:
            con.execute(
                "INSERT OR IGNORE INTO indexed_commits "
                "(repo_path, commit_hash, indexed_at) VALUES (?, ?, ?)",
                (repo_path, commit_hash, now),
            )

    def indexed_commit_count(self, repo_path: str) -> int:
        """How many commits have been indexed for this repo."""
        with sqlite3.connect(self._db) as con:
            return con.execute(
                "SELECT COUNT(*) FROM indexed_commits WHERE repo_path=?",
                (repo_path,),
            ).fetchone()[0]

    # ------------------------------------------------------------------ #
    # Internal                                                              #
    # ------------------------------------------------------------------ #

    def _migrate_scratchpad_to_chroma(self) -> None:
        """One-time migration: embed existing SQLite facts into ChromaDB scratchpad.

        Called on every startup but is a no-op when the ChromaDB collection is
        already in sync. This ensures users who had facts before the Phase 3
        upgrade still get semantic search on their existing data.
        """
        chroma_count = self._scratch_col.count()
        sqlite_count = self.fact_count()
        if chroma_count >= sqlite_count or sqlite_count == 0:
            return  # already in sync

        # Fetch all facts not yet embedded
        with sqlite3.connect(self._db) as con:
            rows = con.execute("SELECT id, fact, tags FROM scratchpad").fetchall()

        try:
            existing_ids = set(self._scratch_col.get(include=[])["ids"])
        except Exception:
            existing_ids = set()

        to_embed = [(r[0], r[1], r[2]) for r in rows if r[0] not in existing_ids]
        if not to_embed:
            return

        self._scratch_col.upsert(
            ids=[r[0] for r in to_embed],
            documents=[r[1] for r in to_embed],
            metadatas=[{"tags": r[2]} for r in to_embed],
        )

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
