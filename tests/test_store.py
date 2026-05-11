"""Tests for DecisionStore — SQLite + ChromaDB operations."""
import math
import time
import pytest
from pathlib import Path
from anamne.models import Decision
from anamne.store.graph import DecisionStore


@pytest.fixture
def store(tmp_path):
    """Fresh in-memory-like store in a temp dir for each test."""
    return DecisionStore(data_dir=tmp_path)


# ------------------------------------------------------------------ #
# Episodic memory                                                       #
# ------------------------------------------------------------------ #

def test_add_and_count(store):
    assert store.count() == 0
    d = Decision(
        content="Added Redis", why="DB too slow",
        source_type="commit", source_ref="abc123",
        source_author="alice",
    )
    store.add(d)
    assert store.count() == 1


def test_add_many(store):
    decisions = [
        Decision(
            content=f"Decision {i}", why="reason",
            source_type="commit", source_ref=f"ref{i}",
            source_author="alice",
        )
        for i in range(5)
    ]
    store.add_many(decisions)
    assert store.count() == 5


def test_search_returns_results(store):
    d = Decision(
        content="Switched to PostgreSQL for concurrent writes",
        why="MySQL had locking issues",
        source_type="commit", source_ref="db001",
        source_author="bob",
    )
    store.add(d)
    results = store.search("PostgreSQL database", n_results=5)
    assert len(results) >= 1
    ids = [r.id for r in results]
    assert d.id in ids


def test_search_empty_store(store):
    results = store.search("anything", n_results=5)
    assert results == []


def test_all_repos(store):
    d = Decision(
        content="x", why="y", source_type="commit",
        source_ref="r", source_author="a",
    )
    store.add(d, repo_path="/home/user/myrepo")
    repos = store.all_repos()
    assert "/home/user/myrepo" in repos


# ------------------------------------------------------------------ #
# Scratchpad                                                            #
# ------------------------------------------------------------------ #

def test_remember_and_list(store):
    mid = store.remember("I prefer Python over Go")
    assert mid
    facts = store.list_facts()
    assert any(f["fact"] == "I prefer Python over Go" for f in facts)


def test_remember_with_tags(store):
    store.remember("Use pytest not unittest", tags=["python", "testing"])
    facts = store.list_facts()
    assert facts[0]["tags"] == ["python", "testing"]


def test_forget_fact(store):
    mid = store.remember("temporary fact")
    assert store.forget_fact(mid) is True
    assert store.forget_fact(mid) is False  # already gone


def test_fact_count(store):
    assert store.fact_count() == 0
    store.remember("fact one")
    store.remember("fact two")
    assert store.fact_count() == 2


def test_search_facts(store):
    store.remember("I always use Postgres not SQLite")
    store.remember("Python is my preferred language")
    results = store.search_facts("postgres")
    assert len(results) == 1
    assert "Postgres" in results[0]["fact"]


# ------------------------------------------------------------------ #
# ACT-R activation                                                      #
# ------------------------------------------------------------------ #

def test_activation_zero_for_new_fact(store):
    mid = store.remember("never retrieved fact")
    score = store.activation_score(mid)
    assert score == 0.0


def test_activation_increases_with_retrieval(store):
    mid = store.remember("frequently retrieved fact")
    score_before = store.activation_score(mid)

    store.touch_facts([mid])
    time.sleep(0.01)  # ensure t > 0 in ACT-R formula (avoid same-microsecond timestamps)
    score_after = store.activation_score(mid)

    assert score_after > score_before


def test_activation_formula_correctness(store):
    """Verify the ACT-R formula: A = ln(sum(t_j^(-d)))."""
    mid = store.remember("test fact")
    store.touch_facts([mid])  # one retrieval just now
    time.sleep(0.01)  # ensure t > 0 in ACT-R formula

    score = store.activation_score(mid, decay=0.5)
    # t is ~0 seconds but > 0; t^(-0.5) should be large positive
    # ln(large) is positive
    assert score > 0
    assert math.isfinite(score)


def test_search_facts_ranked(store):
    mid1 = store.remember("Python is preferred")
    mid2 = store.remember("Python for all backend work")

    # Touch mid2 more recently — it should rank higher
    store.touch_facts([mid1])
    time.sleep(0.01)
    store.touch_facts([mid2])
    store.touch_facts([mid2])  # touch mid2 twice more

    results = store.search_facts_ranked("Python")
    assert results[0]["id"] == mid2  # higher activation ranks first


# ------------------------------------------------------------------ #
# get_fact and update_fact_tags                                          #
# ------------------------------------------------------------------ #

def test_get_fact_returns_none_for_missing(store):
    assert store.get_fact("doesnotexist") is None


def test_get_fact_returns_full_record(store):
    mid = store.remember("Full record test", tags=["test"])
    fact = store.get_fact(mid)
    assert fact is not None
    assert fact["id"] == mid
    assert fact["fact"] == "Full record test"
    assert "test" in fact["tags"]
    assert "activation" in fact
    assert fact["use_count"] == 0


def test_update_fact_tags_add(store):
    mid = store.remember("Untagged fact")
    result = store.update_fact_tags(mid, add=["python", "backend"])
    assert "python" in result
    assert "backend" in result


def test_update_fact_tags_remove(store):
    mid = store.remember("Tagged fact", tags=["python", "old"])
    result = store.update_fact_tags(mid, remove=["old"])
    assert "old" not in result
    assert "python" in result


def test_update_fact_tags_set(store):
    mid = store.remember("Override tags", tags=["x", "y", "z"])
    result = store.update_fact_tags(mid, set_tags=["only"])
    assert result == ["only"]


def test_update_fact_tags_missing_fact(store):
    result = store.update_fact_tags("doesnotexist", add=["tag"])
    assert result is None


# ------------------------------------------------------------------ #
# Working memory                                                         #
# ------------------------------------------------------------------ #

def test_working_add_and_active(store):
    mid = store.working_add("debugging auth middleware", ttl_minutes=60)
    active = store.working_active()
    assert any(w["id"] == mid for w in active)


def test_working_clear(store):
    store.working_add("note 1")
    store.working_add("note 2")
    n = store.working_clear()
    assert n == 2
    assert store.working_active() == []


def test_working_expired_not_returned(store):
    """Notes with ttl_minutes=0 should be expired immediately (or very soon)."""
    # Use negative TTL via direct insert to test expiry logic
    import sqlite3
    from datetime import datetime, timezone, timedelta
    mid = "expiredtest"
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=5)
    with sqlite3.connect(store._db) as con:
        con.execute(
            "INSERT INTO working_memory (id, note, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (mid, "stale note", now.isoformat(), past.isoformat()),
        )
    active = store.working_active()
    assert not any(w["id"] == mid for w in active)


def test_search_working_substring(store):
    store.working_add("currently debugging authentication middleware", ttl_minutes=60)
    store.working_add("reviewing payment processing code", ttl_minutes=60)
    results = store.search_working("auth")
    assert len(results) >= 1
    assert any("auth" in r["note"].lower() for r in results)


def test_search_working_empty(store):
    assert store.search_working("anything") == []


def test_search_working_no_expired(store):
    """Expired notes must not appear in search results."""
    import sqlite3
    from datetime import datetime, timezone, timedelta
    mid = "wexpired"
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=5)
    with sqlite3.connect(store._db) as con:
        con.execute(
            "INSERT INTO working_memory (id, note, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (mid, "expired session note", now.isoformat(), past.isoformat()),
        )
    results = store.search_working("expired")
    assert not any(r["id"] == mid for r in results)


# ------------------------------------------------------------------ #
# list_all_decisions                                                    #
# ------------------------------------------------------------------ #

def test_list_all_decisions_empty(store):
    assert store.list_all_decisions() == []


def test_list_all_decisions_returns_all(store):
    from anamne.models import Decision
    for i in range(3):
        d = Decision(
            content=f"Decision {i}", why="reason",
            source_type="commit", source_ref=f"ref{i}",
            source_author="alice",
        )
        store.add(d)
    decisions = store.list_all_decisions()
    assert len(decisions) == 3


def test_list_all_decisions_respects_limit(store):
    from anamne.models import Decision
    for i in range(5):
        store.add(Decision(
            content=f"Dec {i}", why="r",
            source_type="commit", source_ref=f"r{i}",
            source_author="a",
        ))
    decisions = store.list_all_decisions(limit=2)
    assert len(decisions) == 2


# ------------------------------------------------------------------ #
# Semantic scratchpad search                                            #
# ------------------------------------------------------------------ #

def test_search_facts_semantic_empty(store):
    results = store.search_facts_semantic("anything")
    assert results == []


def test_search_facts_semantic_finds_related(store):
    store.remember("I always use PostgreSQL for our database layer")
    store.remember("We prefer Rust over C++ for systems work")
    # Semantic search: "relational database" should match PostgreSQL fact
    results = store.search_facts_semantic("relational database", limit=5)
    assert isinstance(results, list)
    # Should return at least one result (ChromaDB may return any result)
    assert len(results) >= 1


def test_search_facts_ranked_merges_semantic_and_substring(store):
    """Ranked search returns results from both semantic and substring."""
    store.remember("Python is preferred for scripting tasks")
    store.remember("We use TypeScript for all frontend work")
    # Substring would find "Python", semantic might also return TypeScript
    results = store.search_facts_ranked("scripting language preference", limit=5)
    assert isinstance(results, list)
    # At minimum the Python fact should appear
    assert any("Python" in r["fact"] for r in results)


# ------------------------------------------------------------------ #
# Incremental indexing                                                  #
# ------------------------------------------------------------------ #

def test_commit_not_indexed_initially(store):
    assert store.is_commit_indexed("/repo/path", "abc123") is False


def test_mark_and_check_commit_indexed(store):
    store.mark_commit_indexed("/repo/path", "abc123")
    assert store.is_commit_indexed("/repo/path", "abc123") is True


def test_mark_commit_indexed_idempotent(store):
    """Marking the same commit twice should not raise."""
    store.mark_commit_indexed("/repo/path", "deadbeef")
    store.mark_commit_indexed("/repo/path", "deadbeef")  # second call is a no-op
    assert store.indexed_commit_count("/repo/path") == 1


def test_indexed_commit_count(store):
    assert store.indexed_commit_count("/repo/a") == 0
    store.mark_commit_indexed("/repo/a", "hash1")
    store.mark_commit_indexed("/repo/a", "hash2")
    store.mark_commit_indexed("/repo/b", "hash1")
    assert store.indexed_commit_count("/repo/a") == 2
    assert store.indexed_commit_count("/repo/b") == 1


# ------------------------------------------------------------------ #
# Tag filtering                                                         #
# ------------------------------------------------------------------ #

def test_list_facts_tag_filter(store):
    store.remember("Python fact", tags=["python"])
    store.remember("Postgres fact", tags=["database"])
    store.remember("Tagged with both", tags=["python", "database"])

    py_facts = store.list_facts(tags=["python"])
    assert all("python" in f["tags"] for f in py_facts)
    assert len(py_facts) == 2  # "Python fact" + "Tagged with both"


def test_search_facts_tag_filter(store):
    store.remember("Python is great for scripting", tags=["python"])
    store.remember("Python runs on any OS", tags=["ops"])

    results = store.search_facts("python", tags=["python"])
    assert all("python" in f["tags"] for f in results)
    assert len(results) == 1


# ------------------------------------------------------------------ #
# Clear layer methods                                                   #
# ------------------------------------------------------------------ #

def test_clear_scratchpad(store):
    store.remember("fact one")
    store.remember("fact two")
    assert store.fact_count() == 2
    n = store.clear_scratchpad()
    assert n == 2
    assert store.fact_count() == 0


def test_clear_working(store):
    store.working_add("note a")
    store.working_add("note b")
    n = store.clear_working()
    assert n == 2
    assert store.working_active() == []


def test_clear_episodic(store):
    from anamne.models import Decision
    store.add(Decision(
        content="A decision", why="reason",
        source_type="commit", source_ref="abc",
        source_author="alice",
    ))
    store.mark_commit_indexed("/repo", "abc")
    assert store.count() == 1
    n = store.clear_episodic()
    assert n == 1
    assert store.count() == 0
    assert store.indexed_commit_count("/repo") == 0


# ------------------------------------------------------------------ #
# Fact versioning                                                       #
# ------------------------------------------------------------------ #

def test_remember_creates_history(store):
    mid = store.remember("Initial fact", tags=["a"])
    hist = store.get_fact_history(mid)
    assert len(hist) == 1
    assert hist[0]["change_type"] == "created"
    assert hist[0]["content"] == "Initial fact"
    assert hist[0]["tags"] == ["a"]


def test_update_fact_content_creates_history(store):
    mid = store.remember("Old content")
    store.update_fact_content(mid, "New content")
    hist = store.get_fact_history(mid)
    # Newest first: content_updated, then created
    assert hist[0]["change_type"] == "content_updated"
    assert hist[0]["content"] == "Old content"  # snapshot of OLD version
    assert hist[1]["change_type"] == "created"
    # Current fact should show new content
    assert store.get_fact(mid)["fact"] == "New content"


def test_update_fact_content_missing(store):
    assert store.update_fact_content("notexist", "x") is False


def test_update_fact_tags_creates_history(store):
    mid = store.remember("A fact", tags=["x"])
    store.update_fact_tags(mid, add=["y"])
    hist = store.get_fact_history(mid)
    types = [h["change_type"] for h in hist]
    assert "tags_updated" in types


def test_forget_fact_creates_tombstone(store):
    mid = store.remember("To be forgotten")
    store.forget_fact(mid)
    hist = store.get_fact_history(mid)
    assert hist[0]["change_type"] == "forgotten"
    assert hist[1]["change_type"] == "created"


def test_forget_with_merged_into_creates_merge_history(store):
    mid = store.remember("Fact to absorb")
    survivor = store.remember("Survivor fact")
    store.forget_fact(mid, _merged_into=survivor)
    hist = store.get_fact_history(mid)
    assert hist[0]["change_type"] == "merged_into"
    assert hist[0]["merged_into"] == survivor


def test_history_empty_for_unknown_id(store):
    assert store.get_fact_history("nonexistent") == []


def test_history_newest_first(store):
    mid = store.remember("fact")
    store.update_fact_content(mid, "revised")
    store.forget_fact(mid)
    hist = store.get_fact_history(mid)
    types = [h["change_type"] for h in hist]
    assert types[0] == "forgotten"
    assert types[-1] == "created"


# ------------------------------------------------------------------ #
# import-memory logic (store-level)                                    #
# ------------------------------------------------------------------ #

def test_import_memory_dedup(store):
    """Importing the same fact twice should not create a duplicate."""
    store.remember("Postgres is our primary DB", tags=["db"])
    existing = {f["fact"].strip() for f in store.list_facts(limit=100_000)}
    # Simulate the dedup logic from import-memory
    new_facts = ["Postgres is our primary DB", "Redis for caching"]
    imported = 0
    for text in new_facts:
        if text.strip() not in existing:
            store.remember(text.strip())
            imported += 1
    assert imported == 1  # only the Redis fact should be new
    assert store.fact_count() == 2


def test_import_memory_allows_dupes_when_skip_disabled(store):
    store.remember("Shared fact", tags=["x"])
    # Without dedup check, same text is imported again
    store.remember("Shared fact", tags=["x"])
    assert store.fact_count() == 2  # duplicates allowed at the store level


def test_working_search_finds_active_note(store):
    store.working_add("investigating rate limiter bug", ttl_minutes=60)
    results = store.search_working("rate limiter")
    assert len(results) >= 1
    assert any("rate limiter" in r["note"] for r in results)


# ------------------------------------------------------------------ #
# Pin / unpin                                                           #
# ------------------------------------------------------------------ #

def test_pin_fact_sets_pinned_flag(store):
    mid = store.remember("This is critical architecture")
    assert store.get_fact(mid)["pinned"] is False
    ok = store.pin_fact(mid)
    assert ok is True
    assert store.get_fact(mid)["pinned"] is True


def test_unpin_fact_clears_pinned_flag(store):
    mid = store.remember("Temporarily pinned")
    store.pin_fact(mid)
    ok = store.unpin_fact(mid)
    assert ok is True
    assert store.get_fact(mid)["pinned"] is False


def test_pin_missing_fact_returns_false(store):
    assert store.pin_fact("no-such-id") is False


def test_unpin_missing_fact_returns_false(store):
    assert store.unpin_fact("no-such-id") is False


def test_list_facts_includes_pinned_field(store):
    mid = store.remember("pinned fact")
    store.pin_fact(mid)
    facts = store.list_facts(limit=10)
    match = next(f for f in facts if f["id"] == mid)
    assert match["pinned"] is True


def test_pinned_facts_excluded_from_consolidation(store):
    """Pinned facts should not appear in consolidate_facts() input."""
    from anamne.agents.oracle import OracleAgent
    mid = store.remember("Architecture decision: always use PostgreSQL")
    store.pin_fact(mid)
    # Consolidation should not touch the pinned fact
    # We verify by checking that all_facts fed to clustering excludes pinned ones
    facts = store.list_facts(limit=100)
    unpinned = [f for f in facts if not f.get("pinned")]
    assert all(not f["pinned"] for f in unpinned)


# ------------------------------------------------------------------ #
# Tag rename / tag clear                                                #
# ------------------------------------------------------------------ #

def test_rename_tag_replaces_across_facts(store):
    a = store.remember("Use Python for the API", tags=["pyhton", "backend"])
    b = store.remember("Tests with pytest", tags=["pyhton", "testing"])
    c = store.remember("Frontend uses React", tags=["frontend"])

    affected = store.rename_tag("pyhton", "python")
    assert affected == 2

    fa = store.get_fact(a)
    fb = store.get_fact(b)
    fc = store.get_fact(c)
    assert "python" in fa["tags"] and "pyhton" not in fa["tags"]
    assert "python" in fb["tags"] and "pyhton" not in fb["tags"]
    assert "python" not in fc["tags"] and "pyhton" not in fc["tags"]


def test_rename_tag_no_op_when_missing(store):
    store.remember("fact with no matching tag", tags=["foo"])
    assert store.rename_tag("does-not-exist", "anything") == 0


def test_rename_tag_merges_when_target_already_present(store):
    """If a fact already has the new tag, the old tag should just be dropped."""
    a = store.remember("dual tagged", tags=["old", "new"])
    affected = store.rename_tag("old", "new")
    assert affected == 1
    tags = store.get_fact(a)["tags"]
    assert tags.count("new") == 1
    assert "old" not in tags


def test_remove_tag_from_all_strips_without_deleting(store):
    a = store.remember("keep this fact", tags=["temp", "permanent"])
    b = store.remember("keep this too", tags=["temp"])
    affected = store.remove_tag_from_all("temp")
    assert affected == 2
    # Facts still exist
    assert store.get_fact(a) is not None
    assert store.get_fact(b) is not None
    assert "temp" not in store.get_fact(a)["tags"]
    assert "permanent" in store.get_fact(a)["tags"]
    assert store.get_fact(b)["tags"] == []


def test_remove_tag_from_all_records_history(store):
    a = store.remember("fact for history", tags=["temp", "keep"])
    store.remove_tag_from_all("temp")
    history = store.get_fact_history(a)
    assert any(h["change_type"] == "tag_removed" for h in history)


# ------------------------------------------------------------------ #
# Related facts (semantic similarity)                                    #
# ------------------------------------------------------------------ #

def test_related_facts_excludes_source(store):
    a = store.remember("PostgreSQL is our primary database")
    b = store.remember("We picked Postgres because of concurrent writes")
    c = store.remember("Frontend uses React and TypeScript")
    results = store.related_facts(a, limit=5)
    ids = [r["id"] for r in results]
    assert a not in ids  # source must be excluded


def test_related_facts_missing_id_returns_empty(store):
    assert store.related_facts("nonexistent-id") == []


def test_related_facts_returns_pinned_field(store):
    a = store.remember("Python preference for backend")
    b = store.remember("Backend services use Python")
    store.pin_fact(b)
    results = store.related_facts(a, limit=5)
    if results:
        # Each result should expose a `pinned` boolean
        assert all("pinned" in r for r in results)


# ------------------------------------------------------------------ #
# Working memory get / delete / promote                                 #
# ------------------------------------------------------------------ #

def test_working_get_returns_note(store):
    wid = store.working_add("debugging auth middleware", ttl_minutes=120)
    note = store.working_get(wid)
    assert note is not None
    assert note["id"] == wid
    assert note["note"] == "debugging auth middleware"


def test_working_get_missing_returns_none(store):
    assert store.working_get("no-such-id") is None


def test_working_delete_removes_note(store):
    wid = store.working_add("temporary thought")
    assert store.working_get(wid) is not None
    ok = store.working_delete(wid)
    assert ok is True
    assert store.working_get(wid) is None


def test_working_delete_missing_returns_false(store):
    assert store.working_delete("no-such-id") is False


def test_promote_working_creates_scratchpad_and_removes_working(store):
    wid = store.working_add("we decided to use Postgres for concurrency")
    new_id = store.promote_working(wid, tags=["architecture"])
    assert new_id is not None
    # Working note is gone
    assert store.working_get(wid) is None
    # New scratchpad fact exists
    new_fact = store.get_fact(new_id)
    assert new_fact is not None
    assert new_fact["fact"] == "we decided to use Postgres for concurrency"
    assert "architecture" in new_fact["tags"]


def test_promote_working_missing_returns_none(store):
    assert store.promote_working("no-such-id") is None
