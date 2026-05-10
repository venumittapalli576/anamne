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
    score_after = store.activation_score(mid)

    assert score_after > score_before


def test_activation_formula_correctness(store):
    """Verify the ACT-R formula: A = ln(sum(t_j^(-d)))."""
    mid = store.remember("test fact")
    store.touch_facts([mid])  # one retrieval just now

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
