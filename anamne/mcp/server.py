"""
ANAMNE MCP Server  - plug into Cursor, Claude Code, or any MCP client.

Exposes 22 memory tools covering all three LIGHT layers:
  Episodic  : ask_why, search_decisions, get_file_context, get_stats
  Scratchpad: remember, list_facts, forget_fact, get_fact, tag_fact,
              update_fact, get_fact_history, search_facts, consolidate_facts,
              pin_fact, unpin_fact, related_facts, mark_fact
  Working   : working_memory_add, working_memory_active, search_working_memory,
              promote_working
  Meta      : benchmark_recall (measure retrieval quality, local/no key)
"""

from __future__ import annotations

from fastmcp import FastMCP

from anamne import __version__
from anamne.agents.oracle import OracleAgent
from anamne.store.graph import DecisionStore

mcp = FastMCP(
    name="anamne",
    version=__version__,
    instructions=(
        "ANAMNE is a brain-inspired personal memory layer. "
        "Use remember() to store facts the user wants kept across sessions. "
        "Use ask_why() or recall via search_decisions() to surface relevant memory. "
        "Use working_memory_add() for short-lived session context. "
        "Use get_file_context() before editing a file to understand its history. "
        "Use consolidate_facts() periodically to merge redundant scratchpad entries."
    ),
)

_store = DecisionStore()
_oracle: OracleAgent | None = None


def _get_oracle() -> OracleAgent:
    """Lazy Oracle construction.

    The Oracle eagerly initialises an LLMClient, which raises when neither
    ANTHROPIC_API_KEY nor GEMINI_API_KEY is set. By deferring construction
    until an LLM-dependent tool is actually called, the MCP server can boot
    in 'partial mode' - the 18 non-LLM tools (search_facts, list_facts,
    remember, working_memory_*, pin_fact, related_facts, etc.) work normally.
    Only ask_why and consolidate_facts will surface the missing-key error.
    """
    global _oracle
    if _oracle is None:
        _oracle = OracleAgent(store=_store)
    return _oracle


@mcp.tool()
def ask_why(question: str) -> str:
    """
    Ask why a piece of code exists or why an architectural decision was made.

    Examples:
      - "Why is authentication using opaque tokens instead of JWT?"
      - "Why was the database switched from MySQL to PostgreSQL?"
      - "Why does the payment service exist separately?"
    """
    try:
        return _get_oracle().ask(question)
    except Exception as e:
        return (
            "ask_why is unavailable: no LLM API key configured. "
            "Set ANTHROPIC_API_KEY or GEMINI_API_KEY (run `anamne doctor` "
            f"for details). Underlying error: {e}"
        )


@mcp.tool()
def search_decisions(query: str, limit: int = 5) -> list[dict]:
    """
    Search the decision knowledge base and return raw decision records.

    Returns a list of decision dicts with: content, why, source_type,
    source_ref, source_author, created_at, file_paths.
    """
    decisions = _store.search(query, n_results=limit)
    return [d.to_dict() for d in decisions]


@mcp.tool()
def get_file_context(file_path: str) -> str:
    """
    Get all architectural decisions related to a specific file.

    Use this before editing a file to understand WHY it was built this way.
    Returns a markdown summary of relevant decisions.
    """
    decisions = _store.search(file_path, n_results=10)
    file_decisions = [
        d for d in decisions
        if any(file_path in fp for fp in d.file_paths)
        or file_path.split("/")[-1] in d.content.lower()
    ]

    if not file_decisions:
        return f"No specific decisions found for `{file_path}`. Try `ask_why` with a broader question."

    lines = [f"## Decisions related to `{file_path}`\n"]
    for d in file_decisions:
        lines.append(
            f"**{d.content}**  \n"
            f"Why: {d.why}  \n"
            f"Source: {d.source_type} `{d.short_ref}` by {d.source_author} "
            f"({d.created_at.strftime('%Y-%m-%d')})\n"
        )
    return "\n".join(lines)


@mcp.tool()
def get_stats() -> dict:
    """Get statistics about the ANAMNE knowledge base."""
    count = _store.count()
    repos = _store.all_repos()
    return {
        "total_decisions": count,
        "indexed_repos": repos,
        "facts_in_scratchpad": _store.fact_count(),
        "working_memory_items": len(_store.working_active()),
        "status": "ready" if count > 0 else "empty",
        "hint": "Run: anamne index <repo-path>" if count == 0 else None,
    }


@mcp.tool()
def remember(fact: str, tags: list[str] | None = None) -> dict:
    """
    Store a durable fact in scratchpad memory (brain-inspired semantic memory).

    Use this when the user shares something worth remembering across sessions:
    preferences, project context, personal facts, recurring constraints.

    Returns the memory id.
    """
    mem_id = _store.remember(fact, tags=tags)
    return {"id": mem_id, "stored": fact, "tags": tags or []}


@mcp.tool()
def list_facts(limit: int = 30) -> list[dict]:
    """
    List durable facts in scratchpad memory, most-recently-used first.
    Useful for getting a quick view of what the user has asked you to remember.
    """
    return _store.list_facts(limit=limit)


@mcp.tool()
def forget_fact(memory_id: str) -> dict:
    """Forget a specific scratchpad fact by id."""
    ok = _store.forget_fact(memory_id)
    return {"id": memory_id, "removed": ok}


@mcp.tool()
def working_memory_add(note: str, ttl_minutes: int = 60) -> dict:
    """
    Add a short-lived note to working memory (auto-expires).

    Use for session-specific context: 'currently debugging the login flow',
    'testing PR #42', 'the user is in a hurry'. Decays automatically.
    """
    mem_id = _store.working_add(note, ttl_minutes=ttl_minutes)
    return {"id": mem_id, "note": note, "ttl_minutes": ttl_minutes}


@mcp.tool()
def working_memory_active() -> list[dict]:
    """Return active (non-expired) working memory items, newest first."""
    return _store.working_active()


@mcp.tool()
def search_working_memory(query: str, limit: int = 10) -> list[dict]:
    """Semantic + substring search over active working-memory notes.

    Only searches non-expired notes. Useful for finding a specific session
    context note when you have many active items.
    """
    return _store.search_working(query, limit=limit)


@mcp.tool()
def search_facts(
    query: str,
    limit: int = 10,
    tags: list[str] | None = None,
) -> list[dict]:
    """Hybrid search over scratchpad facts (substring + semantic), ranked by ACT-R activation.

    Optionally filter by one or more tags. Tags are ANDed: a fact must have
    at least one of the provided tags to appear in results.

    Examples:
      search_facts("postgres")
      search_facts("auth", tags=["security", "backend"])
    """
    results = _store.search_facts_ranked(query, limit=limit * 2 if tags else limit)
    if tags:
        tag_set = set(tags)
        results = [f for f in results if tag_set.intersection(f.get("tags", []))]
    return results[:limit]


@mcp.tool()
def get_fact(memory_id: str) -> dict | None:
    """Get full details for a specific scratchpad fact by id.

    Returns the fact, tags, created_at, last_used_at, use_count, and
    ACT-R activation score. Returns null if the id doesn't exist.
    """
    return _store.get_fact(memory_id)


@mcp.tool()
def tag_fact(
    memory_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    set_tags: list[str] | None = None,
) -> dict:
    """Add, remove, or replace tags on a scratchpad fact.

    - add: tags to add to existing tags
    - remove: tags to remove from existing tags
    - set_tags: replace all tags with exactly these (ignores add/remove)

    Returns {id, tags} with the updated tag list, or {error} if not found.
    """
    result = _store.update_fact_tags(memory_id, add=add, remove=remove, set_tags=set_tags)
    if result is None:
        return {"error": f"No fact found with id: {memory_id}"}
    return {"id": memory_id, "tags": result}


@mcp.tool()
def update_fact(memory_id: str, content: str) -> dict:
    """Update the text content of a scratchpad fact.

    The old version is preserved in fact_history for auditability.
    Returns {id, updated: true} on success or {error} if not found.
    """
    ok = _store.update_fact_content(memory_id, content)
    if not ok:
        return {"error": f"No fact found with id: {memory_id}"}
    return {"id": memory_id, "updated": True, "new_content": content}


@mcp.tool()
def get_fact_history(memory_id: str) -> list[dict]:
    """Return the full change history for a scratchpad fact, newest first.

    Each entry has: seq, fact_id, content, tags, changed_at, change_type,
    and merged_into (non-null when the fact was absorbed by consolidation).

    change_type values: created | content_updated | tags_updated | forgotten | merged_into
    """
    return _store.get_fact_history(memory_id)


@mcp.tool()
def consolidate_facts(
    dry_run: bool = False,
    threshold: float = 0.6,
) -> dict:
    """
    Merge redundant scratchpad facts using LLM consolidation (ACC-style).

    Groups semantically similar facts by keyword overlap, then merges each
    group into a single clean statement. Inspired by the Agent Cognitive
    Compressor's bounded-state design and sleep-phase memory consolidation.

    Args:
        dry_run: if True, returns the merge plan without writing anything.
        threshold: Jaccard similarity threshold for grouping (0.0-1.0).
    """
    try:
        agent = _get_oracle()
    except Exception as e:
        return {
            "error": "consolidate_facts requires an LLM API key. "
                     "Set ANTHROPIC_API_KEY or GEMINI_API_KEY.",
            "detail": str(e),
        }
    merges = agent.consolidate_facts(similarity_threshold=threshold, dry_run=dry_run)
    return {
        "merges": len(merges),
        "dry_run": dry_run,
        "details": [
            {
                "merged": m["merged"],
                "replaced_count": len(m["replaced"]),
                "replaced_ids": m["replaced"],
            }
            for m in merges
        ],
    }


@mcp.tool()
def pin_fact(memory_id: str) -> dict:
    """Pin a scratchpad fact so it is never auto-consolidated.

    Pinned facts are excluded from consolidate_facts() and the watch daemon.
    Use this for critical, high-confidence facts that must never be merged
    or reworded by the LLM — architecture decisions, hard constraints, etc.

    Returns {id, pinned: true} on success or {error} if not found.
    """
    ok = _store.pin_fact(memory_id)
    if not ok:
        return {"error": f"No fact found with id: {memory_id}"}
    return {"id": memory_id, "pinned": True}


@mcp.tool()
def unpin_fact(memory_id: str) -> dict:
    """Remove the pin from a scratchpad fact.

    After unpinning, the fact is eligible for auto-consolidation again.
    Returns {id, pinned: false} on success or {error} if not found.
    """
    ok = _store.unpin_fact(memory_id)
    if not ok:
        return {"error": f"No fact found with id: {memory_id}"}
    return {"id": memory_id, "pinned": False}


@mcp.tool()
def related_facts(memory_id: str, limit: int = 10) -> list[dict]:
    """Find scratchpad facts most semantically similar to a given fact.

    Uses ChromaDB nearest-neighbor query on the source fact's text. Excludes
    the source itself. Returns a list of {id, fact, tags, pinned}.

    Useful for surfacing hidden duplicates or related context that exact
    keyword search would miss.
    """
    return _store.related_facts(memory_id, limit=limit)


@mcp.tool()
def promote_working(working_id: str, tags: list[str] | None = None) -> dict:
    """Promote a working-memory note into a permanent scratchpad fact.

    The working note is removed; a new scratchpad fact is created with the
    same text and the optional tags. Returns {old_working_id, new_fact_id}
    on success or {error} if the working note doesn't exist.
    """
    new_id = _store.promote_working(working_id, tags=tags)
    if new_id is None:
        return {"error": f"No working note with id: {working_id}"}
    return {"old_working_id": working_id, "new_fact_id": new_id}


@mcp.tool()
def benchmark_recall(k: int = 5) -> dict:
    """Benchmark ANAMNE's own retrieval quality on a curated memory dataset.

    Runs a fully local, no-API-key retrieval benchmark in a throwaway store
    (the user's real memory is never touched) and reports, per strategy,
    recall@k, hit@1, MRR@k, and p50/p95 latency. Useful for answering
    "how good is my memory recall?" or for verifying an upgrade didn't
    regress retrieval quality.

    Returns the structured results dict plus a one-line `headline` summary.
    """
    from anamne.bench import run_benchmark, summary_line

    result = run_benchmark(k=k)
    result["headline"] = summary_line(result)
    return result


@mcp.tool()
def mark_fact(memory_id: str, note: str) -> dict:
    """Attach a free-text audit note to a fact's history.

    Records a `note` change_type entry in fact_history. The fact content
    is NOT modified. Use this for marginalia like "verified 2026-05-11" or
    "linked to ADR-042". Visible via get_fact_history().

    Returns {id, note, ok} on success or {error} if the fact doesn't exist.
    """
    import json as _json
    import sqlite3
    from datetime import datetime, timezone

    fact = _store.get_fact(memory_id)
    if fact is None:
        return {"error": f"No fact found with id: {memory_id}"}
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(_store._db) as con:
        con.execute(
            "INSERT INTO fact_history "
            "(fact_id, content, tags, changed_at, change_type, merged_into) "
            "VALUES (?, ?, ?, ?, 'note', NULL)",
            (memory_id, note, _json.dumps(fact["tags"]), now),
        )
    return {"id": memory_id, "note": note, "ok": True}


def run() -> None:
    """Entry point - runs the MCP server via stdio (for Claude Code / Cursor).

    show_banner=False is critical: MCP uses stdio for JSON-RPC, so anything
    written to stdout other than the protocol corrupts the handshake and the
    host (Claude Code, Cursor) silently rejects the server.
    """
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    run()
