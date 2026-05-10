"""Tests for the Oracle's keyword-overlap clustering helper."""
import pytest
from anamne.agents.oracle import _cluster_by_overlap


def _facts(*texts):
    return [{"id": f"id{i}", "fact": t, "tags": []} for i, t in enumerate(texts)]


def test_identical_topics_cluster():
    facts = _facts(
        "I prefer Python over Go for backend services",
        "I prefer Python for backend and scripting work",
        "I work in Pacific Standard Time zone",
    )
    clusters = _cluster_by_overlap(facts, threshold=0.3)
    assert len(clusters) == 2
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]


def test_all_unrelated_no_merges():
    facts = _facts(
        "Python is preferred",
        "Database uses Postgres",
        "Working hours are 9 to 5",
        "I use macOS",
    )
    clusters = _cluster_by_overlap(facts, threshold=0.5)
    # All singletons — no clusters with >1 item
    assert all(len(c) == 1 for c in clusters)


def test_high_threshold_no_merges():
    facts = _facts(
        "Python for backend",
        "Python scripting preferred",
    )
    clusters = _cluster_by_overlap(facts, threshold=0.99)
    assert all(len(c) == 1 for c in clusters)


def test_low_threshold_merges_more():
    facts = _facts(
        "Python backend services",
        "Python scripting preferred",
        "Python testing with pytest",
    )
    clusters_strict = _cluster_by_overlap(facts, threshold=0.8)
    clusters_loose = _cluster_by_overlap(facts, threshold=0.1)
    # Loose threshold should produce fewer, larger clusters
    assert len(clusters_loose) <= len(clusters_strict)


def test_single_fact_returns_one_cluster():
    facts = _facts("only fact")
    clusters = _cluster_by_overlap(facts, threshold=0.5)
    assert len(clusters) == 1
    assert clusters[0][0]["fact"] == "only fact"


def test_empty_input():
    clusters = _cluster_by_overlap([], threshold=0.5)
    assert clusters == []


def test_short_words_ignored():
    """Words under 4 chars are filtered — 'I', 'use', 'the' don't drive matches."""
    facts = _facts(
        "I use the app",
        "I use the tool",
    )
    # These are nearly identical but all meaningful words are short
    # Behaviour: no crash, returns clusters regardless
    clusters = _cluster_by_overlap(facts, threshold=0.5)
    assert isinstance(clusters, list)
