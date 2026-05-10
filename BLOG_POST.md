# I Built a Tool, Found a Competitor, Read Two Research Papers, and Pivoted in 48 Hours

*A software engineering war story about rapid iteration, research literacy, and the right time to stop.*

---

## The Original Idea

Every codebase has a graveyard of decisions. Why did we switch from MySQL to Postgres? Why does the
payment service live in a separate repo? Why is there a Redis cluster when the database handles
sessions fine?

These answers live in Slack threads, ancient commit messages, people's heads. They're lost as soon
as the team grows or memory fades. I wanted to fix that.

The idea: index git history with an LLM, extract "why" decisions from commit messages and ADRs,
store them in a searchable graph, and surface them via an MCP server directly in your editor.

I called it **ANAMNE** and built it in a weekend.

```bash
anamne index ./my-repo
anamne ask "why was Redis added to this codebase?"
```

It worked. Claude answered with citations from actual commit messages. The demo was clean.

---

## The Competitor Problem

Then I did what you should always do before claiming novelty: searched for existing tools.

**Repowise** does exactly what I built. So does **GitMind**. Multiple well-funded products with
better UI, more integrations, and a head start.

The first reaction: rebuild something else. Start over. Find a gap that doesn't exist yet.

I nearly did. I spent hours searching for "the next idea" — AI memory tools, code documentation
generators, context compression systems. Every category had competition. Some had more than one.

The actual lesson wasn't "the idea is wrong." It was: **this is 2026. Every obvious idea has
competition.** Starting over doesn't solve that.

---

## The Research Pivot

Instead of rebuilding, I read papers.

Three caught my eye:

**LIGHT** (arXiv 2510.27246) — a 2026 paper proposing a three-layer memory architecture for AI
agents. The analogy to human memory was explicit:

- *Episodic memory* (hippocampal long-term store): full records of past events
- *Scratchpad* (semantic memory): distilled facts and truths
- *Working memory* (prefrontal cortex): what you're holding in your head right now

The paper showed that combining all three layers with explicit conflict resolution produced
significantly better recall than single-store approaches.

**Agent Cognitive Compressor** — "bounded compressed state": as an AI's memory grows, you can't
fit all of it in the context window. The solution is hierarchical: keep the top-K items verbatim,
compress the lower-priority tail into a compact summary. This bounds the prompt size regardless of
how much history you've stored.

**ACT-R memory architecture** — cognitive science model of how humans retrieve memories. Key
insight: retrieval probability isn't just about relevance — it's modulated by recency and frequency
of use. Items used more recently and more often have higher "activation" and are more likely to be
retrieved.

Reading these, I realized: **my architecture was already halfway there.** I had ChromaDB for
semantic search (episodic), SQLite for structured storage, and an LLM for synthesis. The core
pieces were right. I just needed to implement the full three-layer design and ground the
abstractions in the actual papers.

---

## What Changed

Over two days I refactored ANAMNE from "git WHY tool" to "personal memory layer":

**Layer 1 — Episodic memory** (already existed, renamed/clarified):
- ChromaDB semantic search over all past decisions
- SQLite for bi-temporal storage (created_at, valid_until)
- Indexed from git history, ADR files

**Layer 2 — Scratchpad** (new):
- Explicit `remember()` API for durable facts
- LLM-based distillation: paste a wall of text, get N atomic facts extracted
- ACT-R activation tracking: `last_used`, `use_count` updated on every recall
- `forget()` for explicit deletion
- `consolidate()` to merge redundant facts (analogous to sleep-phase consolidation)

**Layer 3 — Working memory** (new):
- Short-lived session notes with TTL expiry
- "Currently debugging the auth middleware" — gone in an hour without action
- No LLM call needed, pure recency-weighted retrieval

**Oracle agent** (refactored):
- Queries all three layers simultaneously
- Formats with explicit citations: `[episodic #3]`, `[fact #a2b1]`, `[working]`
- ACC-style bounded context: top 3 verbatim + tail compressed into a summary
- Layer conflict resolution (scratchpad beats working beats episodic)

**New capture paths** (Phase 2):
- `anamne journal` — timestamped entry, one command, no ceremony
- `anamne import-chat` — point at an exported Claude/ChatGPT JSON, extract durable facts

---

## The Design That Emerged

The thing I realized while implementing this: **the problem I'm solving is different from Repowise's.**

Repowise solves "why was this code written this way?" for teams. It's a knowledge management tool
for codebases.

ANAMNE solves "what do I know about everything I've worked on?" for individuals. It's a
personal memory layer that works across all your AI tools, all your projects, your preferences,
your constraints, your history.

Those are different markets. One is team-facing (requires enterprise sales, permission models,
onboarding). The other is individual-facing (one-command install, local-first, bring your own key).

The pivot didn't require rebuilding anything. It required reframing the problem.

---

## What the Code Looks Like

The Oracle agent — the core of the recall system — ends up surprisingly clean:

```python
def ask(self, question: str, ...) -> str:
    # Pull from all three layers
    episodic = self._store.search(question, n_results=8)
    facts = self._store.search_facts(question, limit=8)
    working = self._store.working_active()[:10]

    # ACT-R: update activation on retrieved facts
    if facts:
        self._store.touch_facts([f["id"] for f in facts])

    # ACC: top-3 verbatim, tail compressed
    verbatim = episodic[:3]
    tail = episodic[3:]
    compressed = self._compress_tail(tail, question) if tail else None

    # Format with citations, send to LLM
    prompt = _ORACLE_PROMPT.format(
        working=self._format_working(working),
        facts=self._format_facts(facts),
        decisions=self._format_decisions(verbatim),
        compressed_section=f"BACKGROUND: {compressed}\n\n" if compressed else "",
        question=question,
    )
    return self._llm.complete(prompt, max_tokens=2048).text
```

Every claim in the answer is cited back to its layer and entry. The LLM is instructed to surface
staleness warnings and call out conflicts between layers.

The consolidation step — analogous to sleep-phase memory consolidation in neuroscience — clusters
scratchpad facts by keyword overlap and merges each cluster via LLM:

```bash
$ anamne consolidate --dry-run

Merge 1:
  - I prefer Python for backend services
  - I prefer Python over Go for scripting
  -> Prefer Python over Go for all backend and scripting work

Merge 2:
  - Database uses PostgreSQL
  - Switched from MySQL to Postgres in 2024 for better JSON support
  -> Using PostgreSQL (migrated from MySQL in 2024 for native JSON support)
```

---

## What Surprised Me

**Reading papers was faster than searching for ideas.** The four papers I read took maybe three
hours total. They gave me a clear design vocabulary (episodic, semantic, working memory), specific
algorithms (ACT-R activation formula, ACC compression), and actual citations I can put in the README.

That's worth more than any "find a gap" exercise.

**The competitive landscape is a feature, not a bug.** Yes, Mem0 and Supermemory exist. They're
building cloud SDKs for developers. I'm building a local-first tool for individual AI users. The
fact that there's a funded market means people want this — I'm just serving a different slice of it.

**"Brain-inspired" is a useful metaphor, not a liability.** I was initially worried it would sound
like marketing fluff. But grounding it in actual papers — LIGHT, ACT-R, hippocampal indexing
theory — makes it defensible. When someone asks "why three layers?", I have a real answer.

---

## The Honest Assessment

ANAMNE is a personal portfolio project. It won't replace Mem0. It won't scale to teams.

What it is:
- A working CLI demo with cited recall across three memory layers
- A real MCP server (tested with Claude Code and Cursor)
- A brain-inspired memory architecture grounded in actual 2026 research papers
- An honest README that doesn't overclaim

What it demonstrates:
- The ability to read research papers and translate them into working code
- Rapid iteration under uncertainty (pivot in 48 hours, don't rebuild)
- Engineering judgment (scope-appropriate design, no overengineering)

The "build a thing, find a competitor, read papers, pivot" story is more interesting to a
hiring manager than "I built X, here is the feature list."

---

## What's Next

Phase 2 is already started:
- `anamne import-chat` — import exported Claude/ChatGPT conversations, extract facts
- `anamne journal` — one-command timestamped notes, no ceremony

The interesting open question is Phase 3: **ACT-R decay**. Right now "activation" is tracked
(last_used, use_count) but there's no actual decay formula. The real ACT-R formula is:

```
activation = ln(Σ t_i^(-d)) + noise
```

where `t_i` is the recency of each retrieval and `d` is the decay parameter. Implementing that
would make the "brain-inspired" claim genuinely precise rather than loosely metaphorical.

---

## Code

[github.com/venumittapalli576/anamne](https://github.com/venumittapalli576/anamne)

MIT license. One-command install. Bring your own key. Zero telemetry.

```bash
pip install anamne
anamne init
```
