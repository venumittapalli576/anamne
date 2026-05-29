"""Tests for the retrieval benchmark (dataset integrity + harness behaviour).

These run fully local with no API key - retrieval uses ChromaDB's bundled
ONNX embedder. The harness always builds a throwaway store, so none of these
tests touch the user's real ~/.anamne data.
"""
import pytest

from anamne.bench import (
    STRATEGIES,
    best_strategy,
    load_dataset,
    run_benchmark,
    summary_line,
)
from anamne.store.graph import DecisionStore


# ------------------------------------------------------------------ #
# Dataset integrity                                                     #
# ------------------------------------------------------------------ #

def test_dataset_loads():
    ds = load_dataset()
    assert ds["facts"], "dataset has no facts"
    assert ds["queries"], "dataset has no queries"


def test_fact_ids_unique():
    ds = load_dataset()
    ids = [f["id"] for f in ds["facts"]]
    assert len(ids) == len(set(ids)), "duplicate fact ids in dataset"


def test_query_ids_unique():
    ds = load_dataset()
    ids = [q["id"] for q in ds["queries"]]
    assert len(ids) == len(set(ids)), "duplicate query ids in dataset"


def test_every_relevant_id_exists():
    """A query that points at a non-existent fact id can never be satisfied."""
    ds = load_dataset()
    fact_ids = {f["id"] for f in ds["facts"]}
    for q in ds["queries"]:
        assert q["relevant_ids"], f"{q['id']} has no relevant_ids"
        missing = [r for r in q["relevant_ids"] if r not in fact_ids]
        assert not missing, f"{q['id']} references unknown fact ids: {missing}"


def test_query_types_known():
    ds = load_dataset()
    allowed = {"keyword", "paraphrase", "multi", "distractor"}
    for q in ds["queries"]:
        assert q.get("type") in allowed, f"{q['id']} has unexpected type {q.get('type')!r}"


# ------------------------------------------------------------------ #
# Harness                                                               #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="module")
def bench_result():
    """Run the full benchmark once (embedding is the slow part) and reuse."""
    return run_benchmark(k=5)


def test_result_shape(bench_result):
    ds = load_dataset()
    assert bench_result["num_facts"] == len(ds["facts"])
    assert bench_result["num_queries"] == len(ds["queries"])
    assert set(bench_result["strategies"]) == set(STRATEGIES)


def test_metrics_in_range(bench_result):
    for name, s in bench_result["strategies"].items():
        assert 0.0 <= s["recall_at_k"] <= 1.0, name
        assert 0.0 <= s["hit_at_1"] <= 1.0, name
        assert 0.0 <= s["mrr_at_k"] <= 1.0, name
        assert s["p50_ms"] >= 0.0 and s["p95_ms"] >= 0.0, name


def test_semantic_recall_is_strong(bench_result):
    """Semantic search should comfortably beat the literal-substring floor.

    Threshold is deliberately loose (>= 0.5) so the test survives minor
    embedding-model changes while still catching a real regression.
    """
    assert bench_result["strategies"]["semantic"]["recall_at_k"] >= 0.5


def test_hybrid_at_least_as_good_as_substring(bench_result):
    sub = bench_result["strategies"]["substring"]["recall_at_k"]
    hyb = bench_result["strategies"]["hybrid"]["recall_at_k"]
    assert hyb >= sub


def test_best_strategy_prefers_production(bench_result):
    """On a fresh store hybrid ties semantic; the tie-break must pick hybrid."""
    assert best_strategy(bench_result) == "hybrid"


def test_summary_line_is_useful(bench_result):
    line = summary_line(bench_result)
    assert "recall@5" in line
    assert "no API key" in line


def test_strategy_subset_runs_only_chosen():
    result = run_benchmark(k=5, strategies=["substring"])
    assert set(result["strategies"]) == {"substring"}


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        run_benchmark(strategies=["does-not-exist"])


def test_runs_in_isolated_dir_without_touching_real_data(tmp_path):
    """When given a data_dir, the harness seeds exactly that dir.

    This is the isolation guarantee: the benchmark builds its own store and
    never reads or writes the user's real memory. We verify by pointing it at
    a temp dir and confirming the dataset facts landed there.
    """
    ds = load_dataset()
    run_benchmark(k=5, data_dir=tmp_path)
    store = DecisionStore(data_dir=tmp_path)
    assert store.fact_count() == len(ds["facts"])
