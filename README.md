# PROVENANCE

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

## What PROVENANCE Does

PROVENANCE runs locally on your machine and gives every AI tool you use a shared memory layer.

```bash
# Remember something
provenance remember "I always use Postgres, not SQLite, because we need concurrent writes"
provenance journal "Finally fixed the Stripe webhook double-fire: the idempotency key was wrong"

# Import an entire Claude or ChatGPT conversation and extract the facts
provenance import-chat ~/Downloads/conversations.json

# Index your git history — every architectural decision extracted automatically
provenance index ./my-repo

# Ask anything — recall across all memory layers with citations
provenance recall "what database decisions have we made?"
```

When you open Claude or Cursor, the AI already knows what matters — through the MCP server.

---

## Memory Architecture

PROVENANCE implements a three-layer memory architecture based on two 2026 research papers
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
pip install provenance-ai
provenance init
```

The wizard detects your API keys and picks a model. You can also set one manually:

| Model | How | Cost | Quality |
|---|---|---|---|
| Gemini 2.5 Flash Lite | `GEMINI_API_KEY=...` in `.env` | Free tier | Good |
| Claude Sonnet 4.6 | `ANTHROPIC_API_KEY=...` in `.env` | ~$0.003/commit | Best |
| Ollama (llama3.2) | `MODEL=ollama/llama3.2` + run `ollama serve` | Free, offline | Good |

Data is stored in `~/.provenance/` — SQLite + ChromaDB. Nothing leaves your machine.

---

## Commands

### Memory capture

```bash
# Add a durable fact (short form — stored verbatim)
provenance remember "we deploy on Fridays before 2pm only"

# Add with tags
provenance remember "prefer pytest over unittest" --tag python --tag testing

# Extract multiple structured facts from a long blob of text (LLM-distilled)
provenance remember "long paste of meeting notes..." --distill

# Log a timestamped journal entry (auto-tagged 'journal')
provenance journal "Switched payment processor because Stripe fees hit 3%"

# Import facts from an exported Claude or ChatGPT conversation
provenance import-chat ~/Downloads/conversations.json
provenance import-chat session.txt --source text --dry-run  # preview first
```

### Memory recall

```bash
# Recall anything — searches all three layers, cited answer
provenance recall "why did we switch from MySQL?"

# Search raw facts in scratchpad (fast, no LLM call)
provenance facts

# Show active working memory
provenance working

# Add a session note to working memory (expires in 60 min by default)
provenance working "currently debugging the auth middleware"
provenance working "debugging login flow" --ttl 120  # 2 hours
```

### Memory maintenance

```bash
# Delete a specific fact by ID
provenance forget <memory-id>

# Merge redundant/duplicate facts using LLM (sleep-phase consolidation)
provenance consolidate --dry-run   # preview first
provenance consolidate             # apply

# Bulk index a git repo — extracts architectural decisions from commit history
provenance index ./my-project
provenance index ./my-project --adr-dir ./docs/adr

# Show memory stats
provenance status
```

### MCP server

```bash
provenance mcp-server  # stdio transport — for Claude Code, Cursor, Cline
```

---

## MCP Integration

PROVENANCE exposes 11 tools through the MCP protocol, giving any compatible AI assistant
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
    "provenance": {
      "command": "provenance",
      "args": ["mcp-server"]
    }
  }
}
```

### Cursor

Settings > MCP > Add server:
```json
{ "command": "provenance mcp-server" }
```

Once connected, Claude/Cursor can call `ask_why`, `remember`, and the other tools directly —
without you copying and pasting context into every new chat.

---

## Quick Demo

```bash
# Create a test repo with realistic history
python scripts/create_test_repo.py

# Index it
provenance index ./test-repo

# Ask questions
provenance recall "why was Redis added?"
provenance recall "what's the payment architecture?"

# Add your own facts
provenance remember "we always review security implications before shipping auth changes"
provenance journal "Migrated from Heroku to Railway today — better pricing for our usage"
provenance recall "what have we decided about deployment?"
```

---

## Research Grounding

This is not a from-scratch design. PROVENANCE implements ideas from:

- **LIGHT** ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246)) — three-layer memory framework:
  episodic + scratchpad + working, with layer-priority conflict resolution
- **Agent Cognitive Compressor** — bounded compressed state: top-K verbatim, tail compressed
- **ACT-R Memory Architecture** — activation tracking (last_used, use_count) for relevance ranking
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
PROVENANCE is for individual humans who use AI tools daily:

- **Local-first** — your data stays on your machine
- **Zero dependencies on external backends** — SQLite + ChromaDB, runs anywhere
- **Open source MIT** — fork it, change it, own it
- **Works with any MCP-compatible tool** — not tied to one vendor

---

## License

MIT. Open source. Bring your own key. Zero telemetry.
