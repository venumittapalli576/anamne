"""
PROVENANCE MCP Server — plug into Cursor, Claude Code, or any MCP client.

Tools exposed:
  ask_why           — answer WHY questions about the codebase
  search_decisions  — raw search returning decision records
  get_file_context  — all decisions related to a specific file
  get_stats         — knowledge base stats
"""

from __future__ import annotations

from fastmcp import FastMCP

from provenance.agents.oracle import OracleAgent
from provenance.store.graph import DecisionStore

mcp = FastMCP(
    name="provenance",
    instructions=(
        "PROVENANCE is the WHY layer of your codebase. "
        "Use ask_why to understand architectural decisions. "
        "Use search_decisions to find relevant past decisions. "
        "Use get_file_context before editing a file to understand its history."
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
    """Get statistics about the PROVENANCE knowledge base."""
    count = _store.count()
    repos = _store.all_repos()
    return {
        "total_decisions": count,
        "indexed_repos": repos,
        "status": "ready" if count > 0 else "empty",
        "hint": "Run: provenance index <repo-path>" if count == 0 else None,
    }


def run() -> None:
    """Entry point — runs the MCP server via stdio (for Claude Code / Cursor)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
