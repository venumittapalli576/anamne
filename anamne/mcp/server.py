"""
ANAMNE MCP Server — plug into Cursor, Claude Code, or any MCP client.

Exposes 11 memory tools covering all three LIGHT layers:
  Episodic : ask_why, search_decisions, get_file_context, get_stats
  Scratchpad: remember, list_facts, forget_fact, search_facts, consolidate_facts
  Working  : working_memory_add, working_memory_active
"""

from __future__ import annotations

from fastmcp import FastMCP

from anamne.agents.oracle import OracleAgent
from anamne.store.graph import DecisionStore

mcp = FastMCP(
    name="anamne",
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
_oracle = OracleAgent(store=_store)


@mcp.tool()
def ask_why(question: str) -> str:
    """
    Ask why a piece of code exists or why an architectural decision was made.

    Examples:
      - "Why is authentication using opaque tokens instead of JWT?"
      - "Why was the database switched from MySQL to PostgreSQL?"
      - "Why does the payment service exist separately?"
    """
    return _oracle.ask(question)


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
def search_facts(query: str, limit: int = 10) -> list[dict]:
    """Substring search over scratchpad facts, ranked by ACT-R activation (recency + frequency)."""
    return _store.search_facts_ranked(query, limit=limit)


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
        threshold: Jaccard similarity threshold for grouping (0.0–1.0).
    """
    from anamne.agents.oracle import OracleAgent
    agent = OracleAgent(store=_store)
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


def run() -> None:
    """Entry point - runs the MCP server via stdio (for Claude Code / Cursor).

    show_banner=False is critical: MCP uses stdio for JSON-RPC, so anything
    written to stdout other than the protocol corrupts the handshake and the
    host (Claude Code, Cursor) silently rejects the server.
    """
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    run()
