"""
Oracle Agent — answers WHY questions about the codebase.

Takes a natural language question, searches the knowledge base for
relevant decisions, then asks Claude to synthesise a cited answer.
"""

from __future__ import annotations

from typing import Optional

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from provenance.config import get_settings
from provenance.models import Decision
from provenance.store.graph import DecisionStore

console = Console()

_ORACLE_PROMPT = """\
You are PROVENANCE Oracle — you answer questions about WHY a codebase was \
built or changed a certain way.

You have access to the following decisions extracted from git history, \
commit messages, and architecture docs:

{decisions}

---

Question: {question}

Instructions:
- Answer using ONLY the decisions above. Do not invent anything.
- Be direct and specific. Cite the source (type, ref, author, date) for every claim.
- If a decision seems potentially stale or contradicted by a later one, add a ⚠️ STALE ALERT.
- If the knowledge base doesn't have enough information, say exactly that — \
  suggest running `provenance index <repo>` to build more context.
- Format your answer in clean markdown with headers where useful.

Structure:
## Answer
(direct answer to the WHY)

## Sources
(bullet list: source_type, ref, author, date)

## Warnings
(any staleness concerns — omit this section if none)
"""


class OracleAgent:
    def __init__(self, store: Optional[DecisionStore] = None):
        self._cfg = get_settings()
        self._store = store or DecisionStore()
        self._client = anthropic.Anthropic(api_key=self._cfg.anthropic_api_key)

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def ask(self, question: str, n_context: int = 8) -> str:
        """Ask a WHY question. Returns a markdown-formatted answer string."""
        decisions = self._store.search(question, n_results=n_context)

        if not decisions:
            return (
                "**No decisions found in the knowledge base.**\n\n"
                "Run `provenance index <path-to-repo>` first to build the knowledge graph."
            )

        context = self._format_decisions(decisions)

        response = self._client.messages.create(
            model=self._cfg.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": _ORACLE_PROMPT.format(
                        decisions=context,
                        question=question,
                    ),
                }
            ],
        )

        return response.content[0].text

    def ask_pretty(self, question: str) -> None:
        """Ask and print a rich-formatted answer to the terminal."""
        console.print()
        console.print(
            f"[bold cyan]Oracle[/bold cyan] "
            f"[dim]searching {self._store.count()} decisions...[/dim]"
        )
        console.print()

        answer = self.ask(question)

        console.print(
            Panel(
                Markdown(answer),
                title="[bold green]PROVENANCE[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    # ------------------------------------------------------------------ #
    # Internal                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_decisions(decisions: list[Decision]) -> str:
        lines = []
        for i, d in enumerate(decisions, 1):
            stale_flag = " [POTENTIALLY STALE]" if d.is_stale() else ""
            lines.append(
                f"[{i}]{stale_flag}\n"
                f"  What    : {d.content}\n"
                f"  Why     : {d.why}\n"
                f"  Source  : {d.source_type} {d.short_ref} "
                f"by {d.source_author} on {d.created_at.strftime('%Y-%m-%d')}\n"
                f"  Files   : {', '.join(d.file_paths[:4]) or 'unknown'}"
            )
        return "\n\n".join(lines)
