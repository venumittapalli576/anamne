"""
Oracle Agent - cross-layer memory recall.

Implements LIGHT-inspired three-layer retrieval (arXiv 2510.27246):
- Episodic memory   (long-term decisions, ChromaDB semantic search)
- Scratchpad facts  (durable user-stated facts, substring search)
- Working memory    (short-lived session context, recency-based)

The agent gathers candidates from all three layers, formats them into a
single context block with provenance, and asks the LLM to synthesise a
cited answer using ONLY that context.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from provenance.config import get_settings
from provenance.llm import LLMClient
from provenance.models import Decision
from provenance.store.graph import DecisionStore

console = Console()

_ORACLE_PROMPT = """\
You are PROVENANCE Oracle - you answer questions using only the user's \
personal memory layers below. You combine three brain-inspired memory types \
following the LIGHT framework (arXiv 2510.27246):

WORKING MEMORY (current session, recency-weighted):
{working}

SCRATCHPAD FACTS (durable, user-stated truths):
{facts}

EPISODIC MEMORY (long-term, captured from code/docs/history):
{decisions}

---

Question: {question}

Instructions:
- Answer using ONLY the memory above. Do not invent or assume anything.
- Cite the source layer for every claim: [working], [fact #id], or [episodic #N].
- If multiple layers contradict, prefer scratchpad > working > episodic and call out the conflict.
- If a decision is marked POTENTIALLY STALE, surface that.
- If the memory doesn't contain enough info, say so explicitly and suggest:
    `provenance remember "..."`  to add a fact, or
    `provenance index <repo>`    to capture more episodic memory.
- Be direct and specific. Skip filler.

Structure your answer:

## Answer
(direct, grounded in the memory above)

## Sources
(bullet list — which layer and which entry backed each part of the answer)

## Warnings
(staleness or contradictions — omit this section if there are none)
"""


class OracleAgent:
    def __init__(self, store: Optional[DecisionStore] = None):
        self._cfg = get_settings()
        self._store = store or DecisionStore()
        self._llm = LLMClient(self._cfg)
        self._model = self._llm.model

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def ask(
        self,
        question: str,
        n_episodic: int = 6,
        n_facts: int = 8,
        n_working: int = 10,
    ) -> str:
        """Cross-layer recall. Returns a markdown answer."""
        # 1. Pull candidates from all three layers
        episodic = self._store.search(question, n_results=n_episodic)
        facts = self._store.search_facts(question, limit=n_facts)
        working = self._store.working_active()[:n_working]

        # If everything is empty, bail out early without an LLM call
        if not (episodic or facts or working):
            return (
                "**No memory found.**\n\n"
                "Try one of these to seed the knowledge base:\n"
                '- `provenance remember "..."` to add a durable fact\n'
                "- `provenance index <repo>` to capture git history\n"
                '- `provenance working "..."` to note current session context'
            )

        # 2. Update last_used timestamp on facts we're about to surface
        # (lightweight implementation of activation/usage tracking from ACT-R)
        if facts:
            self._store.touch_facts([f["id"] for f in facts])

        # 3. Format each layer with explicit provenance
        prompt = _ORACLE_PROMPT.format(
            working=self._format_working(working),
            facts=self._format_facts(facts),
            decisions=self._format_decisions(episodic),
            question=question,
        )

        return self._llm.complete(prompt, max_tokens=2048).text

    def ask_pretty(self, question: str) -> None:
        """Ask and print a rich-formatted answer to the terminal."""
        ep_count = self._store.count()
        fact_count = self._store.fact_count()
        work_count = len(self._store.working_active())

        console.print()
        console.print(
            f"[bold cyan]Oracle[/bold cyan] "
            f"[dim]recalling across {ep_count} episodic, "
            f"{fact_count} facts, {work_count} working...[/dim]"
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
    # Layer formatters                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_decisions(decisions: list[Decision]) -> str:
        if not decisions:
            return "(no episodic memory matches)"
        lines = []
        for i, d in enumerate(decisions, 1):
            stale_flag = " [POTENTIALLY STALE]" if d.is_stale() else ""
            lines.append(
                f"[episodic #{i}]{stale_flag}\n"
                f"  What    : {d.content}\n"
                f"  Why     : {d.why}\n"
                f"  Source  : {d.source_type} {d.short_ref} "
                f"by {d.source_author} on {d.created_at.strftime('%Y-%m-%d')}\n"
                f"  Files   : {', '.join(d.file_paths[:4]) or 'unknown'}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _format_facts(facts: list[dict]) -> str:
        if not facts:
            return "(no scratchpad facts match)"
        return "\n".join(
            f"[fact #{f['id']}] {f['fact']}"
            + (f"  (tags: {', '.join(f['tags'])})" if f.get('tags') else "")
            for f in facts
        )

    @staticmethod
    def _format_working(working: list[dict]) -> str:
        if not working:
            return "(working memory is empty)"
        return "\n".join(
            f"[working] {w['note']}  (added {w['created_at']})"
            for w in working
        )
