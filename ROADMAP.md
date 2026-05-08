# PROVENANCE — Roadmap

A local-first, brain-inspired memory layer for AI users. Personal open-source project. MIT.

---

## What's Built (v0.1.0)

- `Decision`/`Memory` data model with bi-temporal fields (created_at, valid_until)
- SQLite + ChromaDB dual store
- Historian Agent — captures memories from git history via LLM
- Oracle Agent — recalls memories with citations
- FastMCP server with 4 tools (`ask_why`, `search_decisions`, `get_file_context`, `get_stats`)
- CLI with `init`, `index`, `ask`, `status`, `mcp-server`
- Working multi-model LLM client (Claude + Gemini)
- One-command setup via `provenance init`

---

## Direction Change

Originally PROVENANCE captured "WHY decisions were made" from git. We discovered Repowise (and others) already do this well in the WHY-layer category.

**v0.2 pivots PROVENANCE into a brain-inspired personal memory layer for AI users.** The core architecture (bi-temporal store + semantic retrieval + MCP server) maps directly onto the LIGHT memory framework from 2026 research. We're reframing what we already built rather than starting over.

---

## Phase 1 — Memory Architecture (next 2 weeks)

**Goal:** Implement the three LIGHT layers cleanly.

- **Episodic memory layer** — refactor existing decisions into the long-term episodic store. Already 90% done.
- **Scratchpad layer** — explicit `remember()` API for distilled facts. New table, simple.
- **Working memory layer** — short-term session state with TTL. New, small. Stores "what I'm working on right now."
- **Cross-layer recall** — Oracle agent queries all three layers and weighs them properly. Mostly refactor.
- **`provenance remember` CLI command** — add fact to scratchpad
- **`provenance recall` CLI command** — generalized version of current `ask`
- **`forget(memory_id)` MCP tool** — explicit deletion matching brain-style decay

---

## Phase 2 — Better Capture (after Phase 1)

- **Clipboard capture** — `provenance capture-clipboard` watches and offers to remember interesting things
- **AI conversation import** — point at exported Claude / ChatGPT / Cursor logs, extract memories
- **Manual journal entry** — quick CLI to log a thought before it's lost

---

## Phase 3 — Polish

- **Web UI** — simple browser view of all memories, filterable
- **Browser extension** — auto-suggest "remember this?" for important things you read
- **Better forgetting** — implement actual ACT-R-style decay (temporal decay + activation frequency)
- **Memory consolidation** — periodic background job that merges related memories (analog of sleep)

---

## What This Project Is Not

Things explicitly out of scope:
- Cloud SaaS — local-first, always
- Developer SDK for app builders — that's Mem0 / Supermemory's market
- Enterprise memory governance — too much surface area for a solo project
- Replacement for AI-tool-native memory features (ChatGPT memory, Claude projects)
- Anything that requires hosting

---

## Honest Limitations

- Quality depends on what you capture. Garbage in, garbage out.
- The "brain-inspired" framing is a useful metaphor, not a neuroscience claim.
- Solo project. Bug reports may sit. Don't depend on this in production.
- Existing competitors (Mem0, Supermemory, MemPalace) are well-funded; this is the open-source, local-first alternative for individuals.

---

## Inspired By

- **LIGHT** ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246)) — three-layer memory framework
- **ACT-R Memory Architecture** — temporal decay + semantic activation
- **Agent Cognitive Compressor** — bounded compressed state
- **Hippocampal indexing theory** — long-term storage as compressed patterns
- **Lore protocol** ([arXiv 2603.15566](https://arxiv.org/abs/2603.15566)) — git-as-knowledge-protocol

---

## Contributing

```bash
git clone https://github.com/venumittapalli576/provenance
cd provenance
pip install -e .
```

PRs welcome. Keep scope small. Reject feature creep.
