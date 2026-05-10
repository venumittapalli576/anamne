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

## What's Built (v0.2.0)

**Pivot:** brain-inspired personal memory layer for AI users, grounded in two 2026 research papers.

| Feature | Source | Status |
|---|---|---|
| Three-layer memory (episodic/scratchpad/working) | LIGHT (arXiv 2510.27246) | ✅ |
| Cross-layer recall with citation | LIGHT retrieval design | ✅ |
| Layer-conflict resolution priority | LIGHT prompt design | ✅ |
| ACT-R activation tracking (last_used + use_count) | ACT-R cognitive arch | ✅ |
| LLM-based fact distillation (`remember --distill`) | LIGHT key-value extraction | ✅ |
| Working memory with TTL decay | Beyond LIGHT | ✅ |
| Bounded context compression (top-K verbatim + tail summary) | Agent Cognitive Compressor | ✅ |
| Scratchpad consolidation (`provenance consolidate`) | ACC + sleep-phase consolidation | ✅ |
| Full MCP tool surface (11 tools) | — | ✅ |

---

## Direction

Originally PROVENANCE captured "WHY decisions were made" from git. Repowise (and others) already do
this well. **v0.2 pivots to a brain-inspired personal memory layer for AI users.** The architecture
maps directly onto the LIGHT memory framework and the ACC bounded-state design from 2026 research.

---

## Phase 2 — Better Capture (next)

- **Clipboard capture** — `provenance capture-clipboard` watches and offers to remember interesting things
- **AI conversation import** — point at exported Claude / ChatGPT / Cursor logs, extract memories
- **Manual journal entry** — quick CLI to log a thought before it's lost

---

## Phase 3 — Polish

- **Web UI** — simple browser view of all memories, filterable
- **Browser extension** — auto-suggest "remember this?" for important things you read
- **ACT-R decay scoring** — proper temporal decay formula (not just last_used recency)
- **Periodic consolidation cron** — auto-consolidate facts on a schedule (analog of sleep)

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
