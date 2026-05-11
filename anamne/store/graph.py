"""
Decision store: SQLite (temporal/relational) + ChromaDB (semantic search).

SQLite holds the full decision records with temporal metadata.
ChromaDB holds the embeddings for semantic similarity search on TWO collections:
  - 'decisions'   - episodic memory (git commits, ADRs)
  - 'scratchpad'  - semantic search over durable facts (Phase 3 upgrade)

Both are embedded  - zero external services required.
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

-- Fact versioning: immutable audit log of every change to scratchpad facts.
-- change_type values: 'created', 'content_updated', 'tags_updated', 'forgotten', 'merged_into'
-- merged_into: fact_id of the surviving merged fact when change_type = 'merged_into'
CREATE TABLE IF NOT EXISTS fact_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id      TEXT NOT NULL,
    content      TEXT NOT NULL,
    tags         TEXT NOT NULL DEFAULT '[]',
    changed_at   TEXT NOT NULL,
    change_type  TEXT NOT NULL,
    merged_into  TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_fact ON fact_history(fact_id);
CREATE INDEX IF NOT EXISTS idx_history_time ON fact_history(changed_at);
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
        # Phase 5: semantic search over working memory notes
        self._working_col = self._chroma.get_or_create_collection(
            name="working_memory",
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
    # Scratchpad  - durable user-provided facts                              #
    # ------------------------------------------------------------------ #

    def remember(self, fact: str, tags: Optional[list[str]] = None) -> str:
        """Add a fact to scratchpad. Returns the new memory id."""
        import uuid
        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(tags or [])
        with sqlite3.connect(self._db) as con:
            con.execute(
                "INSERT INTO scratchpad (id, fact, tags, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (mem_id, fact, tags_json, now, now),
            )
            self._record_history(con, mem_id, fact, tags_json, "created")
        # Also embed into ChromaDB for semantic search
        self._scratch_col.upsert(
            ids=[mem_id],
            documents=[fact],
            metadatas=[{"tags": tags_json}],
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
                "SELECT id, fact, tags, created_at, last_used_at, use_count, "
                "COALESCE(pinned, 0) "
                "FROM scratchpad ORDER BY last_used_at DESC LIMIT ?",
                (limit * 3 if tags else limit,),
            ).fetchall()
        results = [
            {
                "id": r[0], "fact": r[1], "tags": json.loads(r[2]),
                "created_at": r[3], "last_used_at": r[4], "use_count": r[5],
                "pinned": bool(r[6]),
            }
            for r in rows
        ]
        if tags:
            tag_set = set(tags)
            results = [f for f in results if tag_set.intersection(f["tags"])]
        return results[:limit]

    def get_fact(self, mem_id: str) -> Optional[dict]:
        """Return a single scratchpad fact by id, or None if not found."""
        with sqlite3.connect(self._db) as con:
            row = con.execute(
                "SELECT id, fact, tags, created_at, last_used_at, use_count, "
                "COALESCE(pinned, 0) "
                "FROM scratchpad WHERE id = ?",
                (mem_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "fact": row[1], "tags": json.loads(row[2]),
            "created_at": row[3], "last_used_at": row[4], "use_count": row[5],
            "pinned": bool(row[6]),
            "activation": self.activation_score(row[0]),
        }

    def update_fact_tags(
        self,
        mem_id: str,
        add: Optional[list[str]] = None,
        remove: Optional[list[str]] = None,
        set_tags: Optional[list[str]] = None,
    ) -> Optional[list[str]]:
        """Add, remove, or replace tags on an existing scratchpad fact.

        Returns the updated tag list, or None if the fact doesn't exist.
        If set_tags is provided, it replaces all tags entirely.
        """
        current = self.get_fact(mem_id)
        if current is None:
            return None

        if set_tags is not None:
            new_tags = list(set_tags)
        else:
            tag_set = set(current["tags"])
            if add:
                tag_set.update(add)
            if remove:
                tag_set.difference_update(remove)
            new_tags = sorted(tag_set)

        with sqlite3.connect(self._db) as con:
            new_tags_json = json.dumps(new_tags)
            con.execute(
                "UPDATE scratchpad SET tags = ? WHERE id = ?",
                (new_tags_json, mem_id),
            )
            # Record current content for the history snapshot
            row = con.execute(
                "SELECT fact FROM scratchpad WHERE id = ?", (mem_id,)
            ).fetchone()
            if row:
                self._record_history(con, mem_id, row[0], new_tags_json, "tags_updated")
        return new_tags

    def update_fact_content(self, mem_id: str, new_content: str) -> bool:
        """Update the text content of a scratchpad fact, recording the old version.

        Returns True if the fact existed and was updated, False if not found.
        """
        current = self.get_fact(mem_id)
        if current is None:
            return False
        with sqlite3.connect(self._db) as con:
            # Archive old version first
            self._record_history(
                con, mem_id, current["fact"], json.dumps(current["tags"]),
                "content_updated",
            )
            con.execute(
                "UPDATE scratchpad SET fact = ? WHERE id = ?",
                (new_content, mem_id),
            )
        # Re-embed in ChromaDB
        self._scratch_col.upsert(
            ids=[mem_id],
            documents=[new_content],
            metadatas=[{"tags": json.dumps(current["tags"])}],
        )
        return True

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
            count = cur.rowcount
        try:
            ids = self._working_col.get(include=[])["ids"]
            if ids:
                self._working_col.delete(ids=ids)
        except Exception:
            pass
        return count

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

    def forget_fact(self, mem_id: str, _merged_into: Optional[str] = None) -> bool:
        """Delete a scratchpad fact and record a tombstone in fact_history.

        _merged_into: internal  - set by consolidation to link the deletion to the
        surviving merged fact.  Not part of the public API.
        """
        with sqlite3.connect(self._db) as con:
            row = con.execute(
                "SELECT fact, tags FROM scratchpad WHERE id = ?", (mem_id,)
            ).fetchone()
            if not row:
                return False
            change_type = "merged_into" if _merged_into else "forgotten"
            self._record_history(
                con, mem_id, row[0], row[1], change_type, merged_into=_merged_into
            )
            con.execute("DELETE FROM scratchpad WHERE id = ?", (mem_id,))
        try:
            self._scratch_col.delete(ids=[mem_id])
        except Exception:
            pass  # ChromaDB may not have it yet (pre-migration facts)
        return True

    def pin_fact(self, mem_id: str) -> bool:
        """Pin a scratchpad fact so it is never auto-consolidated.

        Returns True if the fact was found and pinned, False if not found.
        """
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "UPDATE scratchpad SET pinned = 1 WHERE id = ?", (mem_id,)
            ).rowcount
        return rows > 0

    def unpin_fact(self, mem_id: str) -> bool:
        """Remove the pin from a scratchpad fact.

        Returns True if the fact was found and unpinned, False if not found.
        """
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "UPDATE scratchpad SET pinned = 0 WHERE id = ?", (mem_id,)
            ).rowcount
        return rows > 0

    def get_fact_history(self, fact_id: str) -> list[dict]:
        """Return the full change history for a scratchpad fact, newest first."""
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "SELECT id, fact_id, content, tags, changed_at, change_type, merged_into "
                "FROM fact_history WHERE fact_id = ? ORDER BY changed_at DESC",
                (fact_id,),
            ).fetchall()
        return [
            {
                "seq": r[0],
                "fact_id": r[1],
                "content": r[2],
                "tags": json.loads(r[3]),
                "changed_at": r[4],
                "change_type": r[5],
                "merged_into": r[6],
            }
            for r in rows
        ]

    def touch_facts(self, mem_ids: list[str]) -> None:
        """Mark facts as used  - updates scratchpad stats AND logs to retrieval_log.

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
        much higher than one retrieved once a week ago  - recency AND
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

    def related_facts(self, mem_id: str, limit: int = 10) -> list[dict]:
        """Find facts most semantically similar to the given fact.

        Uses ChromaDB to query nearest neighbors of the fact's text, excluding
        the source fact itself. Falls back to substring matching on the first
        word if ChromaDB is unavailable.
        """
        source = self.get_fact(mem_id)
        if source is None:
            return []
        total = self.fact_count()
        if total <= 1:
            return []
        try:
            results = self._scratch_col.query(
                query_texts=[source["fact"]],
                n_results=min(limit + 1, total),
            )
        except Exception:
            return []
        ids = results["ids"][0] if results["ids"] else []
        # Exclude the source fact itself
        ids = [i for i in ids if i != mem_id][:limit]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                f"SELECT id, fact, tags, COALESCE(pinned, 0) FROM scratchpad "
                f"WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        id_to_fact = {
            r[0]: {
                "id": r[0],
                "fact": r[1],
                "tags": json.loads(r[2]),
                "pinned": bool(r[3]),
            }
            for r in rows
        }
        return [id_to_fact[i] for i in ids if i in id_to_fact]

    def rename_tag(self, old: str, new: str) -> int:
        """Replace every occurrence of `old` tag with `new` across all facts.

        Returns the number of facts modified. Safe with duplicate-elimination:
        if a fact already has `new`, the rename just drops `old`.
        """
        if not old or not new or old == new:
            return 0
        affected = 0
        with sqlite3.connect(self._db) as con:
            rows = con.execute("SELECT id, fact, tags FROM scratchpad").fetchall()
            for fid, content, tags_json in rows:
                tags = json.loads(tags_json)
                if old not in tags:
                    continue
                new_tags = sorted({(new if t == old else t) for t in tags})
                new_tags_json = json.dumps(new_tags)
                con.execute(
                    "UPDATE scratchpad SET tags = ? WHERE id = ?",
                    (new_tags_json, fid),
                )
                self._record_history(
                    con, fid, content, new_tags_json, "tag_renamed",
                )
                affected += 1
        return affected

    def remove_tag_from_all(self, tag: str) -> int:
        """Remove `tag` from every fact that has it, keeping the facts.

        Returns the number of facts modified. Unlike `forget_tag`, the facts
        themselves are preserved.
        """
        if not tag:
            return 0
        affected = 0
        with sqlite3.connect(self._db) as con:
            rows = con.execute("SELECT id, fact, tags FROM scratchpad").fetchall()
            for fid, content, tags_json in rows:
                tags = json.loads(tags_json)
                if tag not in tags:
                    continue
                new_tags = [t for t in tags if t != tag]
                new_tags_json = json.dumps(new_tags)
                con.execute(
                    "UPDATE scratchpad SET tags = ? WHERE id = ?",
                    (new_tags_json, fid),
                )
                self._record_history(
                    con, fid, content, new_tags_json, "tag_removed",
                )
                affected += 1
        return affected

    def fact_count(self) -> int:
        with sqlite3.connect(self._db) as con:
            return con.execute("SELECT COUNT(*) FROM scratchpad").fetchone()[0]

    # ------------------------------------------------------------------ #
    # Working memory  - short-lived session context                          #
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
        # Embed for semantic search
        self._working_col.upsert(
            ids=[mem_id],
            documents=[note],
            metadatas=[{"expires_at": expires.isoformat()}],
        )
        return mem_id

    def working_active(self) -> list[dict]:
        """Return non-expired working-memory notes, newest first."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._db) as con:
            # Lazy GC: collect expired IDs before deleting
            expired_rows = con.execute(
                "SELECT id FROM working_memory WHERE expires_at < ?", (now,)
            ).fetchall()
            expired_ids = [r[0] for r in expired_rows]
            if expired_ids:
                con.execute("DELETE FROM working_memory WHERE expires_at < ?", (now,))
            rows = con.execute(
                "SELECT id, note, created_at, expires_at "
                "FROM working_memory ORDER BY created_at DESC"
            ).fetchall()
        # Prune expired from ChromaDB too
        if expired_ids:
            try:
                self._working_col.delete(ids=expired_ids)
            except Exception:
                pass
        return [
            {"id": r[0], "note": r[1], "created_at": r[2], "expires_at": r[3]}
            for r in rows
        ]

    def search_working(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search over active working-memory notes.

        Searches only non-expired notes; expired ones are pruned on the fly.
        Falls back to substring matching when ChromaDB is empty.
        """
        # Prune expired first (side-effect: clears ChromaDB stale entries)
        active = self.working_active()
        if not active:
            return []

        # Substring fallback
        q_lower = query.lower()
        substring_hits = [n for n in active if q_lower in n["note"].lower()]

        # Semantic search
        try:
            total = self._working_col.count()
            if total > 0:
                results = self._working_col.query(
                    query_texts=[query],
                    n_results=min(limit, total),
                )
                semantic_ids = set(results["ids"][0]) if results["ids"] else set()
                semantic_hits = [n for n in active if n["id"] in semantic_ids]
            else:
                semantic_hits = []
        except Exception:
            semantic_hits = []

        # Merge and deduplicate
        seen: set[str] = set()
        merged: list[dict] = []
        for n in semantic_hits + substring_hits:
            if n["id"] not in seen:
                seen.add(n["id"])
                merged.append(n)
        return merged[:limit]

    def working_clear(self) -> int:
        with sqlite3.connect(self._db) as con:
            cur = con.execute("DELETE FROM working_memory")
            count = cur.rowcount
        try:
            ids = self._working_col.get(include=[])["ids"]
            if ids:
                self._working_col.delete(ids=ids)
        except Exception:
            pass
        return count

    def working_get(self, work_id: str) -> Optional[dict]:
        """Fetch a single working-memory note by id (active or expired)."""
        with sqlite3.connect(self._db) as con:
            row = con.execute(
                "SELECT id, note, created_at, expires_at "
                "FROM working_memory WHERE id = ?",
                (work_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "note": row[1],
            "created_at": row[2], "expires_at": row[3],
        }

    def working_delete(self, work_id: str) -> bool:
        """Delete one working note by id. Returns True if anything was removed."""
        with sqlite3.connect(self._db) as con:
            rows = con.execute(
                "DELETE FROM working_memory WHERE id = ?", (work_id,)
            ).rowcount
        try:
            self._working_col.delete(ids=[work_id])
        except Exception:
            pass
        return rows > 0

    def promote_working(
        self, work_id: str, tags: Optional[list[str]] = None
    ) -> Optional[str]:
        """Move a working note into permanent scratchpad memory.

        Returns the new scratchpad id, or None if the working note didn't exist.
        The original working note is removed (the note is now permanent).
        """
        note = self.working_get(work_id)
        if note is None:
            return None
        new_id = self.remember(note["note"], tags=tags or [])
        self.working_delete(work_id)
        return new_id

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

    @staticmethod
    def _record_history(
        con: sqlite3.Connection,
        fact_id: str,
        content: str,
        tags_json: str,
        change_type: str,
        merged_into: Optional[str] = None,
    ) -> None:
        """Insert one row into fact_history.  Must be called inside an open connection."""
        now = datetime.now(timezone.utc).isoformat()
        con.execute(
            "INSERT INTO fact_history "
            "(fact_id, content, tags, changed_at, change_type, merged_into) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fact_id, content, tags_json, now, change_type, merged_into),
        )

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
            # Phase 10 migration: add pinned column if it doesn't exist yet
            try:
                con.execute(
                    "ALTER TABLE scratchpad ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass  # Column already exists — safe to ignore

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
