"""
ANAMNE retrieval benchmark harness.

Measures how well ANAMNE *finds the right memory*, which is the part that
actually matters for a memory layer. Everything here runs fully local with
no API key: the only model involved is the local ONNX MiniLM embedder that
ChromaDB already ships with.

The harness is deliberately isolated. It seeds a throwaway store in a fresh
temp directory, runs the benchmark against that, and removes it afterwards.
It never reads, writes, or deletes the user's real ~/.anamne data.

Three retrieval strategies are compared head-to-head on the same queries:

  substring  - LIKE '%query%' over the raw fact text (no embeddings)
  semantic   - ChromaDB nearest-neighbour over fact embeddings
  hybrid     - substring + semantic merged, re-ranked by ACT-R activation
               (this is ANAMNE's production default: search_facts_ranked)

Reported per strategy:

  recall@k   - fraction of each query's relevant facts found in the top k
  hit@1      - fraction of queries whose #1 result is relevant
  mrr@k      - mean reciprocal rank of the first relevant hit
  p50 / p95  - per-query latency in milliseconds
"""

from __future__ import annotations

import gc
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

DATASET_PATH = Path(__file__).parent / "dataset.json"

# Retrieval strategies, keyed by the store method they exercise. Each takes
# (store, query, k) and returns a ranked list of fact dicts with an "id" key.
STRATEGIES: dict[str, Callable] = {
    "substring": lambda store, q, k: store.search_facts(q, limit=k),
    "semantic": lambda store, q, k: store.search_facts_semantic(q, limit=k),
    "hybrid": lambda store, q, k: store.search_facts_ranked(q, limit=k),
}


def load_dataset(path: Optional[Path] = None) -> dict:
    """Load the benchmark dataset JSON (facts + labeled queries)."""
    path = path or DATASET_PATH
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Robust for the small N a benchmark produces."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered) + 0.5) - 1))
    return ordered[rank]


def _query_metrics(retrieved_ids: list[str], relevant: set[str]) -> dict:
    """Compute recall/hit/mrr for a single query against its relevant set."""
    if not relevant:
        return {"recall": 0.0, "hit1": 0.0, "rr": 0.0}
    top = retrieved_ids
    found = relevant.intersection(top)
    recall = len(found) / len(relevant)
    hit1 = 1.0 if top and top[0] in relevant else 0.0
    rr = 0.0
    for i, fid in enumerate(top):
        if fid in relevant:
            rr = 1.0 / (i + 1)
            break
    return {"recall": recall, "hit1": hit1, "rr": rr}


def _seed_store(store, facts: list[dict]) -> dict[str, str]:
    """Seed the temp store with the dataset facts.

    Returns a map from dataset fact id (e.g. "f08") to the random store id
    that remember() generates, so query relevance labels can be translated
    into the ids the search methods actually return.
    """
    id_map: dict[str, str] = {}
    for f in facts:
        store_id = store.remember(f["fact"], tags=f.get("tags") or [])
        id_map[f["id"]] = store_id
    return id_map


def run_benchmark(
    k: int = 5,
    strategies: Optional[list[str]] = None,
    dataset: Optional[dict] = None,
    data_dir: Optional[Path] = None,
) -> dict:
    """Run the retrieval benchmark and return a structured results dict.

    Args:
        k: cut-off for recall@k / mrr@k and how many results to request.
        strategies: subset of STRATEGIES to run (default: all).
        dataset: pre-loaded dataset dict (default: the packaged dataset).
        data_dir: where to build the throwaway store. When None, a fresh
            temp directory is created and removed afterwards. When provided,
            the caller owns the directory and it is left in place.

    The store is always a *new* store seeded only with benchmark facts, so
    this never touches the user's real memory.
    """
    from anamne import __version__
    from anamne.store.graph import DecisionStore

    dataset = dataset or load_dataset()
    chosen = strategies or list(STRATEGIES.keys())
    unknown = [s for s in chosen if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"Unknown strategy/strategies: {unknown}. "
                         f"Choose from {list(STRATEGIES)}.")

    facts = dataset["facts"]
    queries = dataset["queries"]

    owns_tmp = data_dir is None
    work_dir = Path(data_dir) if data_dir else Path(tempfile.mkdtemp(prefix="anamne-bench-"))

    store = None
    try:
        store = DecisionStore(data_dir=work_dir)
        id_map = _seed_store(store, facts)

        results: dict[str, dict] = {}
        for name in chosen:
            fn = STRATEGIES[name]
            per_query = []
            latencies: list[float] = []
            for q in queries:
                relevant = {id_map[r] for r in q["relevant_ids"] if r in id_map}
                t0 = time.perf_counter()
                hits = fn(store, q["query"], k)
                latencies.append((time.perf_counter() - t0) * 1000.0)
                retrieved_ids = [h["id"] for h in hits][:k]
                m = _query_metrics(retrieved_ids, relevant)
                m.update({"id": q["id"], "type": q.get("type", "other")})
                per_query.append(m)

            n = len(per_query)
            recall = sum(m["recall"] for m in per_query) / n
            hit1 = sum(m["hit1"] for m in per_query) / n
            mrr = sum(m["rr"] for m in per_query) / n

            by_type: dict[str, list[float]] = {}
            for m in per_query:
                by_type.setdefault(m["type"], []).append(m["recall"])
            type_recall = {t: sum(v) / len(v) for t, v in by_type.items()}

            results[name] = {
                "recall_at_k": recall,
                "hit_at_1": hit1,
                "mrr_at_k": mrr,
                "p50_ms": _percentile(latencies, 50),
                "p95_ms": _percentile(latencies, 95),
                "recall_by_type": type_recall,
            }

        return {
            "anamne_version": __version__,
            "dataset": dataset.get("name", "unknown"),
            "dataset_version": dataset.get("version", "?"),
            "k": k,
            "num_facts": len(facts),
            "num_queries": len(queries),
            "embedder": "local ONNX MiniLM (no API key)",
            "strategies": results,
        }
    finally:
        # Release ChromaDB's file handles so the temp store can be removed
        # (required on Windows, harmless elsewhere).
        if store is not None:
            store.close()
            store = None
        gc.collect()
        if owns_tmp:
            shutil.rmtree(work_dir, ignore_errors=True)


# When two strategies score identically (e.g. on a fresh store hybrid falls
# back to semantic order because no ACT-R history exists yet), prefer the one
# ANAMNE actually ships as its default so the headline reflects production.
_TIE_BREAK = {"hybrid": 2, "semantic": 1, "substring": 0}


def best_strategy(result: dict) -> str:
    """Name of the strategy with the highest recall@k.

    Ties are broken by mrr, then by production preference (hybrid first).
    """
    strat = result["strategies"]
    return max(
        strat,
        key=lambda s: (
            strat[s]["recall_at_k"],
            strat[s]["mrr_at_k"],
            _TIE_BREAK.get(s, -1),
        ),
    )


def summary_line(result: dict) -> str:
    """One-line headline for the winning strategy - tweet/README ready."""
    best = best_strategy(result)
    s = result["strategies"][best]
    return (
        f"{best} retrieval: {s['recall_at_k'] * 100:.0f}% recall@{result['k']}, "
        f"{s['mrr_at_k']:.2f} MRR, {s['p50_ms']:.1f}ms p50 "
        f"on {result['num_queries']} queries / {result['num_facts']} facts "
        f"- fully local, no API key."
    )
