"""
Oracle Agent - cross-layer memory recall.

Implements a hybrid of two 2026 frameworks:

LIGHT (arXiv 2510.27246) — three-layer retrieval:
  - Episodic memory   (long-term decisions, ChromaDB semantic search)
  - Scratchpad facts  (durable user-stated facts, substring search)
  - Working memory    (short-lived session context, recency-based)

Agent Cognitive Compressor (ACC) — bounded context:
  Top-K episodic results are kept verbatim; the tail is compressed into
  a compact summary so the Oracle prompt never balloons as the database grows.
  This is the core idea from the "bounded compressed state" design in ACC.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from anamne.config import get_settings
from anamne.llm import LLMClient
from anamne.models import Decision
from anamne.store.graph import DecisionStore

console = Console()

# How many episodic items to keep verbatim vs. compress (ACC-style)
_VERBATIM_K = 3
_COMPRESS_AFTER = _VERBATIM_K  # anything beyond this is compressed

_ORACLE_PROMPT = """\
You are ANAMNE Oracle - you answer questions using only the user's \
personal memory layers below. You combine three brain-inspired memory types \
following the LIGHT framework (arXiv 2510.27246):

WORKING MEMORY (current session, recency-weighted):
{working}

SCRATCHPAD FACTS (durable, user-stated truths):
{facts}

EPISODIC MEMORY (long-term, captured from code/docs/history):
{decisions}

{compressed_section}\
---

Question: {question}

Instructions:
- Answer using ONLY the memory above. Do not invent or assume anything.
- Cite the source layer for every claim: [working], [fact #id], or [episodic #N].
- If multiple layers contradict, prefer scratchpad > working > episodic and call out the conflict.
- If a decision is marked POTENTIALLY STALE, surface that.
- If the memory doesn't contain enough info, say so explicitly and suggest:
    `anamne remember "..."`  to add a fact, or
    `anamne index <repo>`    to capture more episodic memory.
- Be direct and specific. Skip filler.

Structure your answer:

## Answer
(direct, grounded in the memory above)

## Sources
(bullet list — which layer and which entry backed each part of the answer)

## Warnings
(staleness or contradictions — omit this section if there are none)
"""

_COMPRESS_PROMPT = """\
You are a memory compressor. Summarise the following architectural decisions \
into ONE compact paragraph (3-5 sentences). Preserve the key facts, dates, \
authors, and file references. Drop all repetition and filler.

Decisions to compress:
{items}

Compact summary (plain text, no markdown):"""

_CONSOLIDATE_PROMPT = """\
You are a memory curator. Below are {n} related facts that a user has stored. \
Merge them into a single, concise, self-contained statement that preserves \
all useful information. Drop redundancy. Keep specific names, dates, and \
constraints. Reply with ONLY the merged fact — no explanation, no markdown.

Facts to merge:
{facts}

Merged fact:"""


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
        n_episodic: int = 8,
        n_facts: int = 8,
        n_working: int = 10,
    ) -> str:
        """Cross-layer recall with ACC-style bounded context. Returns markdown."""
        # 1. Pull candidates from all three layers
        episodic = self._store.search(question, n_results=n_episodic)
        # ACT-R: use activation-ranked search for scratchpad (real decay formula)
        facts = self._store.search_facts_ranked(question, limit=n_facts)
        working = self._store.working_active()[:n_working]

        # If everything is empty, bail out early without an LLM call
        if not (episodic or facts or working):
            return (
                "**No memory found.**\n\n"
                "Try one of these to seed the knowledge base:\n"
                '- `anamne remember "..."` to add a durable fact\n'
                "- `anamne index <repo>` to capture git history\n"
                '- `anamne working "..."` to note current session context'
            )

        # 2. Log this retrieval to the ACT-R retrieval_log (feeds future decay scores)
        if facts:
            self._store.touch_facts([f["id"] for f in facts])

        # 3. ACC-style bounded context: split episodic into verbatim + tail
        verbatim_ep = episodic[:_VERBATIM_K]
        tail_ep = episodic[_COMPRESS_AFTER:]

        compressed_section = ""
        if tail_ep:
            summary = self._compress_tail(tail_ep, question)
            compressed_section = (
                f"BACKGROUND CONTEXT (compressed from {len(tail_ep)} lower-ranked episodic "
                f"items — ACC-style bounded state):\n{summary}\n\n"
            )

        # 4. Format each layer with explicit provenance citations
        prompt = _ORACLE_PROMPT.format(
            working=self._format_working(working),
            facts=self._format_facts(facts),
            decisions=self._format_decisions(verbatim_ep),
            compressed_section=compressed_section,
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
                title="[bold green]ANAMNE[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    def consolidate_facts(
        self,
        similarity_threshold: float = 0.6,
        min_cluster: int = 2,
        dry_run: bool = False,
    ) -> list[dict]:
        """
        Merge semantically redundant scratchpad facts (ACC-style consolidation).

        Clusters facts using keyword overlap (cheap, no embeddings), then
        merges each cluster into a single fact via LLM. Returns a list of
        merge records: {merged: str, replaced: list[str]}.

        If dry_run=True, returns the plan without writing to the store.
        """
        all_facts = self._store.list_facts(limit=500)
        if len(all_facts) < min_cluster:
            return []

        clusters = _cluster_by_overlap(all_facts, threshold=similarity_threshold)
        merges = []

        for cluster in clusters:
            if len(cluster) < min_cluster:
                continue

            fact_texts = "\n".join(f"- {f['fact']}" for f in cluster)
            merged = self._llm.complete(
                _CONSOLIDATE_PROMPT.format(n=len(cluster), facts=fact_texts),
                max_tokens=256,
            ).text.strip()

            merge_record = {
                "merged": merged,
                "replaced": [f["id"] for f in cluster],
                "replaced_facts": [f["fact"] for f in cluster],
            }
            merges.append(merge_record)

            if not dry_run:
                # Delete originals, write merged
                for f in cluster:
                    self._store.forget_fact(f["id"])
                self._store.remember(
                    merged,
                    tags=list({t for f in cluster for t in f.get("tags", [])}),
                )

        return merges

    # ------------------------------------------------------------------ #
    # ACC — bounded context compression                                     #
    # ------------------------------------------------------------------ #

    def _compress_tail(self, tail: list[Decision], question: str) -> str:
        """
        Compress lower-ranked episodic items into a single paragraph.

        This implements the ACC 'bounded compressed state' idea:
        the top-K items are presented verbatim (highest signal);
        the rest are summarised to stay within the context budget.
        """
        items_text = "\n\n".join(
            f"Decision {i + 1}: {d.content}\n"
            f"  Why: {d.why}\n"
            f"  Source: {d.source_type} {d.short_ref} by {d.source_author}"
            for i, d in enumerate(tail)
        )
        result = self._llm.complete(
            _COMPRESS_PROMPT.format(items=items_text),
            max_tokens=300,
        )
        return result.text.strip()

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


# ------------------------------------------------------------------ #
# Clustering helper (no embeddings — cheap keyword overlap)            #
# ------------------------------------------------------------------ #

def _cluster_by_overlap(
    facts: list[dict],
    threshold: float = 0.6,
) -> list[list[dict]]:
    """
    Greedy single-linkage clustering by Jaccard word overlap.

    Not perfect, but O(n²) is fine for hundreds of scratchpad facts,
    and it doesn't need an embedding call.
    """
    import re

    def tokens(text: str) -> set[str]:
        return {w.lower() for w in re.findall(r"\w+", text) if len(w) > 3}

    def jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    token_sets = [tokens(f["fact"]) for f in facts]
    n = len(facts)
    visited = [False] * n
    clusters: list[list[dict]] = []

    for i in range(n):
        if visited[i]:
            continue
        cluster = [facts[i]]
        visited[i] = True
        for j in range(i + 1, n):
            if not visited[j] and jaccard(token_sets[i], token_sets[j]) >= threshold:
                cluster.append(facts[j])
                visited[j] = True
        clusters.append(cluster)

    return clusters
