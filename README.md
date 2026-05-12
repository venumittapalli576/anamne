# ANAMNE

> Local-first, brain-inspired memory for Claude, Cursor, ChatGPT, and any
> MCP-compatible AI tool. Your AI tools remember what you told them — across
> sessions, models, and machines.

[![PyPI](https://img.shields.io/pypi/v/anamne.svg)](https://pypi.org/project/anamne/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)
[![CI](https://github.com/venumittapalli576/anamne/actions/workflows/ci.yml/badge.svg)](https://github.com/venumittapalli576/anamne/actions/workflows/ci.yml)

> **About this project:** Personal open-source project, released under the MIT
> license. **Not a commercial product, not for sale, not seeking compensation.**
> Bug reports and PRs are welcome; support is best-effort and provided on the
> maintainer's own time. No service-level agreement is implied.

---

## What this is

AI tools forget you between sessions. Every new chat starts from zero —
re-explaining what you're building, what you've decided, what your
preferences are.

**ANAMNE is a local memory layer that any MCP-compatible AI can read from
and write to.** You tell it things once. Every Claude / Cursor / ChatGPT
session after that has access through the MCP protocol.

```bash
pip install anamne
anamne init
```

```bash
# Tell it something once
anamne remember "we use Postgres because we need concurrent writes"
anamne journal  "Fixed Stripe webhook double-fire: idempotency key was wrong"

# Ask it later (or have your AI do it via MCP)
anamne ask "why did we pick our database?"
```

That's the loop. Everything else is variations on capture and recall.

---

## Why "brain-inspired"

ANAMNE is built around three memory layers from the
[LIGHT framework](https://arxiv.org/abs/2510.27246) and the
[Agent Cognitive Compressor](https://arxiv.org/abs/2510.27246):

| Layer | What it stores | Decay |
|---|---|---|
| **Episodic** | Git commits, ADRs, architectural decisions | Bi-temporal (`valid_until`) |
| **Scratchpad** | Durable facts you wrote down | ACT-R activation (recency × frequency) |
| **Working** | Active session context, reminders | TTL (auto-expires) |

When you ask a question, all three layers are searched in parallel. Top
results are combined and cited back. Lower-ranked results are compressed
into a single summary before being sent to the LLM — the ACC paper's idea
of *bounded compressed state*.

The framing is a useful metaphor grounded in real research, not a
neuroscience claim.

---

## Setup

```bash
pip install anamne
anamne init
```

The wizard picks a model based on which API key it finds:

| Model | How to enable | Cost | Quality |
|---|---|---|---|
| Gemini 2.5 Flash Lite | `GEMINI_API_KEY=...` in `.env` | Free tier | Good |
| Claude Sonnet 4.6 | `ANTHROPIC_API_KEY=...` in `.env` | ~$0.003/commit | Best |

Data lives in `~/.anamne/` (SQLite + ChromaDB). Nothing leaves your machine.

> **From source:** `git clone https://github.com/venumittapalli576/anamne && pip install -e .`

---

## The MCP integration (why this matters)

Once `anamne init` runs, the same memory is available to every AI tool
that speaks MCP. Add ANAMNE to your client config and Claude / Cursor /
Cline can call `remember`, `ask_why`, `search_facts`, and 18 other tools
directly — no copy-paste, no context windows to refill.

```bash
anamne mcp-config           # print Claude Code config snippet
anamne mcp-config --apply   # write it into ~/.claude.json directly
anamne mcp-config --client cursor
```

The result: when you open Claude on Monday, it already knows what you
decided on Friday. Across machines if you sync `~/.anamne/`.

### MCP troubleshooting

> **"My MCP client connected but no anamne tools appear."**
> The MCP server boots as a subprocess of the host (Claude/Cursor/Cline).
> Use `anamne --version` to confirm at least v1.0.2 is on your `PATH`;
> earlier versions refused to start without an API key.
> Then run `anamne tools` — if it lists 21 tools, the surface is healthy
> and the issue is on the client side (restart it).

> **"`anamne` resolves to an old version."**
> Run `pip install --upgrade anamne` (or `pip install -e .` from a clone).
> The path that ends up in `~/.claude.json` is whatever `anamne.exe`
> resolves to *at the time you ran `mcp-config --apply`* — it doesn't
> update automatically when you upgrade.

> **"Episodic recall doesn't return anything."**
> Run `anamne status` and check `Episodic decisions`. Zero means you
> haven't indexed a repo yet — run `anamne index <path-to-your-repo>`.

> **"How do I verify the integration end-to-end without restarting Claude?"**
> Run `pytest tests/test_mcp_integration.py -v` against a clone of the
> repo. It spawns `anamne mcp-server` as a subprocess and does a real
> MCP `initialize` + `tools/list` handshake. Same code path Claude uses.

---

## The five commands you actually need

```bash
anamne remember "..."         # capture a durable fact
anamne journal  "..."         # timestamped capture (auto-tagged)
anamne ask      "..."         # cross-layer recall with citations (uses LLM)
anamne search   "..."         # fast no-LLM search of scratchpad
anamne mcp-server             # hand the memory to Claude / Cursor / Cline
```

Everything else is convenience on top of these.

---

## Full command surface

The v1.0 stable surface is documented in [STABLE.md](STABLE.md).
Run `anamne --help` for the menu, or `anamne <command> --help` for any
specific one. Highlights:

**Capture:** `remember`, `journal`, `import-web`, `import-chat`,
`capture-clipboard`, `working`

**Recall:** `ask`, `search`, `search-working`

**Manage:** `facts`, `info`, `edit`, `tag`, `pin/unpin`, `forget`,
`prune`, `consolidate`, `dedupe`, `clear`, `forget-tag`, `tag-rename`

**Episodic:** `index <repo>`, `sync <repo>`, `watch`

**Inspect:** `tags`, `status`, `stats`, `history`, `doctor`

**Backup:** `export`, `import-memory`, `backup`

**Interfaces:** `mcp-server`, `mcp-config`, `tools`, `shell`, `ui`

---

## A 60-second tour

```bash
# Capture
anamne remember "I always use pytest, not unittest" --tag python --tag testing
anamne remember "we deploy on Fridays only" --auto-tag

# Bulk import
anamne import-web https://12factor.net
anamne import-chat ~/Downloads/claude-conversation.json

# Index a repo to capture WHY decisions from git history
anamne index ./my-project

# Recall
anamne ask "what's our deploy policy?"
anamne search postgres
anamne facts --tag python

# Browse everything in your browser
anamne ui
```

---

## Honest limitations

- **Output quality depends on what you capture.** Vague memories give
  vague answers.
- **Indexing a large repo costs a few dollars** on paid APIs (free on
  Gemini within rate limits).
- **MCP integration only works in MCP-aware editors** (Claude Code,
  Cursor, Cline, a few others).
- **This is a personal project.** Bug reports may sit for a while. Not
  production infrastructure.
- **The "brain-inspired" framing is a metaphor.** It's grounded in real
  cognitive-architecture research (ACT-R, LIGHT, ACC) but it isn't a
  neuroscience claim.

---

## Why not Mem0 / Supermemory / MemGPT?

Those tools are SDKs for app developers — they require their backend and
target SaaS builders. ANAMNE is for individuals who use AI tools daily.

| | ANAMNE | Mem0 / Supermemory |
|---|---|---|
| Where the data lives | Your machine | Their backend |
| Hosting required | None (SQLite + ChromaDB) | Yes |
| MCP-native | Yes (21 tools) | No |
| Target user | Individual humans | SaaS builders |
| Open source | MIT | Various |

If you want a memory layer for your end-product, use Mem0 or Supermemory.
If you want a memory layer for yourself, use ANAMNE.

---

## Research grounding

- **LIGHT** ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246)) —
  three-layer memory framework with layer-priority conflict resolution
- **ACT-R** (Anderson & Lebiere 1998) — `A_i = ln(Σ t_j^-d)` decay
  formula; every retrieval is timestamped in `retrieval_log`
- **Agent Cognitive Compressor** — bounded compressed state: top-K
  verbatim, tail compressed
- **Hippocampal indexing theory** — long-term storage as compressed
  patterns
- **Lore protocol** ([arXiv 2603.15566](https://arxiv.org/abs/2603.15566))
  — git as a knowledge graph

---

## License

MIT. Open source. Bring your own key. Zero telemetry.

---

## Maintainer notes

Pushing a `vX.Y.Z` tag triggers PyPI publish via Trusted Publishing:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

One-time setup: add a Trusted Publisher at
https://pypi.org/manage/account/publishing/ — repo `venumittapalli576/anamne`,
workflow `publish.yml`, environment `pypi`.
