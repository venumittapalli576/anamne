# ANAMNE

> A local-first, brain-inspired memory layer for Claude, Cursor, ChatGPT, and any MCP-compatible AI tool.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

---

## The Problem

AI tools forget you between sessions. Every time you open a new chat, you re-explain:
- What you're building and why
- What decisions you've already made
- Your preferences and constraints
- What went wrong last week

The context window is not the answer. Even million-token windows lose track of what mattered three sessions ago.

**Structured memory is the answer — the way human brains do it.**

---

## What ANAMNE Does

ANAMNE runs locally on your machine and gives every AI tool you use a shared memory layer.

```bash
# Remember something
anamne remember "I always use Postgres, not SQLite, because we need concurrent writes"
anamne journal "Finally fixed the Stripe webhook double-fire: the idempotency key was wrong"

# Import an entire Claude or ChatGPT conversation and extract the facts
anamne import-chat ~/Downloads/conversations.json

# Index your git history — every architectural decision extracted automatically
anamne index ./my-repo

# Ask anything — recall across all memory layers with citations
anamne recall "what database decisions have we made?"
```

When you open Claude or Cursor, the AI already knows what matters — through the MCP server.

---

## Memory Architecture

ANAMNE implements a three-layer memory architecture based on two 2026 research papers
(LIGHT, Agent Cognitive Compressor) and neuroscience (ACT-R, hippocampal indexing theory):

| Layer | Brain analog | Stores | Decay |
|---|---|---|---|
| **Episodic** | Hippocampal long-term index | Git decisions, ADR files, full history | Bi-temporal (valid_until) |
| **Scratchpad** | Semantic memory | Distilled facts, journal entries, imported chats | ACT-R activation (explicit forget) |
| **Working** | Prefrontal cortex | Current session context, active tasks | TTL (auto-expires) |

When you ask a question, all three layers are searched. The top results from each layer are
combined, conflicts are surfaced, and every answer is cited back to its source.

Additionally, when the episodic database grows large, lower-ranked results are **compressed**
into a compact summary before being sent to the LLM — this is the ACC paper's core idea of
*bounded compressed state*, preventing prompt bloat.

---

## Setup

```bash
pip install anamne
anamne init
```

The wizard detects your API keys and picks a model. You can also set one manually:

| Model | How | Cost | Quality |
|---|---|---|---|
| Gemini 2.5 Flash Lite | `GEMINI_API_KEY=...` in `.env` | Free tier | Good |
| Claude Sonnet 4.6 | `ANTHROPIC_API_KEY=...` in `.env` | ~$0.003/commit | Best |

Data is stored in `~/.anamne/` — SQLite + ChromaDB. Nothing leaves your machine.

---

## Commands

### Memory capture

```bash
# Add a durable fact (short form — stored verbatim)
anamne remember "we deploy on Fridays before 2pm only"

# Add with tags
anamne remember "prefer pytest over unittest" --tag python --tag testing

# Extract multiple structured facts from a long blob of text (LLM-distilled)
anamne remember "long paste of meeting notes..." --distill

# Log a timestamped journal entry (auto-tagged 'journal')
anamne journal "Switched payment processor because Stripe fees hit 3%"

# Import facts from an exported Claude or ChatGPT conversation
anamne import-chat ~/Downloads/conversations.json
anamne import-chat session.txt --source text --dry-run  # preview first
```

### Memory recall

```bash
# Recall anything — searches all three layers, cited answer
anamne recall "why did we switch from MySQL?"

# Direct scratchpad search — fast, ACT-R ranked, no API key needed
anamne search postgres
anamne search "python preference" --limit 5

# List all scratchpad facts
anamne facts

# Show active working memory
anamne working

# Add a session note to working memory (expires in 60 min by default)
anamne working "currently debugging the auth middleware"
anamne working "debugging login flow" --ttl 120  # 2 hours
```

### Memory maintenance

```bash
# Delete a specific fact by ID
anamne forget <memory-id>

# Merge redundant/duplicate facts using LLM (sleep-phase consolidation)
anamne consolidate --dry-run   # preview first
anamne consolidate             # apply

# Bulk index a git repo — extracts architectural decisions from commit history
anamne index ./my-project
anamne index ./my-project --adr-dir ./docs/adr

# Incremental re-index — only new commits since last run
anamne sync ./my-project

# Export all memories to JSON or Markdown (for backup / migration)
anamne export --output backup.json
anamne export --format markdown --output memories.md

# Save clipboard text directly to scratchpad
anamne capture-clipboard
anamne capture-clipboard --distill   # LLM extracts multiple facts

# Show memory stats
anamne status
```

### Auto-maintenance

```bash
# Incremental re-index — only processes new commits since last run (saves API calls)
anamne sync ./my-project

# Background consolidation daemon — periodically merges redundant facts
anamne watch                       # runs every hour
anamne watch --interval 1800       # every 30 minutes
```

### MCP server

```bash
anamne mcp-server  # stdio transport — for Claude Code, Cursor, Cline
```

---

## MCP Integration

ANAMNE exposes 11 tools through the MCP protocol, giving any compatible AI assistant
direct access to your memory layers:

| Tool | What it does |
|---|---|
| `ask_why` | Ask why a piece of code exists (Oracle, all layers, cited) |
| `search_decisions` | Raw semantic search of episodic memory |
| `get_file_context` | All decisions related to a specific file |
| `get_stats` | Memory layer statistics |
| `remember` | Add a fact to scratchpad |
| `list_facts` | List scratchpad facts |
| `forget_fact` | Delete a scratchpad fact |
| `search_facts` | Substring search over scratchpad |
| `consolidate_facts` | Merge redundant facts (ACC-style) |
| `working_memory_add` | Add a session note |
| `working_memory_active` | Get active session context |

### Claude Code

Add to `~/.claude.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "anamne": {
      "command": "anamne",
      "args": ["mcp-server"]
    }
  }
}
```

### Cursor

Settings > MCP > Add server:
```json
{ "command": "anamne mcp-server" }
```

Once connected, Claude/Cursor can call `ask_why`, `remember`, and the other tools directly —
without you copying and pasting context into every new chat.

---

## Quick Demo

```bash
# Create a test repo with realistic history
python scripts/create_test_repo.py

# Index it
anamne index ./test-repo

# Ask questions
anamne recall "why was Redis added?"
anamne recall "what's the payment architecture?"

# Add your own facts
anamne remember "we always review security implications before shipping auth changes"
anamne journal "Migrated from Heroku to Railway today — better pricing for our usage"
anamne recall "what have we decided about deployment?"
```

---

## Research Grounding

This is not a from-scratch design. ANAMNE implements ideas from:

- **LIGHT** ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246)) — three-layer memory framework:
  episodic + scratchpad + working, with layer-priority conflict resolution
- **Agent Cognitive Compressor** — bounded compressed state: top-K verbatim, tail compressed
- **ACT-R Memory Architecture** — real decay formula `A_i = ln(Σ t_j^-d)`: every retrieval is
  timestamped in `retrieval_log`; activation combines recency and frequency for relevance ranking
- **Hippocampal indexing theory** — long-term store as compressed patterns, short-term as binding
- **Lore protocol** ([arXiv 2603.15566](https://arxiv.org/abs/2603.15566)) — git as knowledge graph

The "brain-inspired" framing is a useful metaphor grounded in actual research — not a claim
about neuroscience accuracy.

---

## Honest Limitations

- Output quality depends on what you capture. Vague memories get vague answers.
- Indexing a large repo can cost a few dollars on paid APIs (free on Gemini within rate limits).
- MCP requires an editor that supports the protocol (Claude Code, Cursor, Cline, a few others).
- This is a personal project. Bug reports may sit. Not production infrastructure.
- The brain-inspired framing is a useful metaphor, not a neuroscience claim.

---

## Why Not Mem0 / Supermemory?

Those tools are SDKs for app developers — they require their backend and target SaaS builders.
ANAMNE is for individual humans who use AI tools daily:

- **Local-first** — your data stays on your machine
- **Zero dependencies on external backends** — SQLite + ChromaDB, runs anywhere
- **Open source MIT** — fork it, change it, own it
- **Works with any MCP-compatible tool** — not tied to one vendor

---

## Publishing to PyPI (maintainer notes)

Pushing a `vX.Y.Z` tag triggers the publish workflow automatically via PyPI Trusted Publishing:

```bash
git tag v0.3.0
git push origin v0.3.0
```

One-time setup: add a Trusted Publisher at https://pypi.org/manage/account/publishing/ with:
- Repository: `venumittapalli576/anamne`
- Workflow: `publish.yml`
- Environment: `pypi`

---

## License

MIT. Open source. Bring your own key. Zero telemetry.
