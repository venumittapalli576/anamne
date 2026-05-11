# ANAMNE

> A local-first, brain-inspired memory layer for Claude, Cursor, ChatGPT, and any MCP-compatible AI tool.

[![PyPI version](https://img.shields.io/pypi/v/anamne.svg)](https://pypi.org/project/anamne/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)
[![CI](https://github.com/venumittapalli576/anamne/actions/workflows/ci.yml/badge.svg)](https://github.com/venumittapalli576/anamne/actions/workflows/ci.yml)

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

# Import from a URL — scrape and distill facts automatically
anamne import-web https://docs.python.org/3/library/asyncio.html

# Import an entire Claude or ChatGPT conversation and extract the facts
anamne import-chat ~/Downloads/conversations.json

# Index your git history — every architectural decision extracted automatically
anamne index ./my-repo

# Ask anything — recall across all memory layers with citations
anamne recall "what database decisions have we made?"

# Browse all your memories in a local web dashboard
anamne ui
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

**Fact versioning:** Every change to a scratchpad fact is recorded in an immutable history
log — creates, edits, tag changes, deletions, and merges are all tracked with timestamps.

---

## Setup

```bash
pip install anamne
anamne init
```

That's it — one command installs everything, the wizard handles the rest.

> **From source:** `git clone https://github.com/venumittapalli576/anamne && pip install -e .`

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
# Add a durable fact (stored verbatim)
anamne remember "we deploy on Fridays before 2pm only"
anamne remember "prefer pytest over unittest" --tag python --tag testing

# Let the LLM suggest tags automatically (learns from your existing tags)
anamne remember "we use FastAPI for all new services" --auto-tag

# Extract multiple structured facts from a long blob of text (LLM-distilled)
anamne remember "long paste of meeting notes..." --distill --auto-tag

# Log a timestamped journal entry (auto-tagged 'journal')
anamne journal "Switched payment processor because Stripe fees hit 3%"

# Scrape a web page and distill key facts into scratchpad
anamne import-web https://example.com/architecture-decisions
anamne import-web https://docs.example.com --limit 10 --dry-run

# Crawl an entire site - follows same-domain links (BFS), deduplicates across pages
anamne import-web https://docs.example.com --crawl
anamne import-web https://docs.example.com --crawl --max-pages 50 --limit 10

# Import facts from an exported Claude or ChatGPT conversation
anamne import-chat ~/Downloads/conversations.json
anamne import-chat session.txt --source text --dry-run  # preview first

# Read clipboard and save as a scratchpad fact
anamne capture-clipboard
anamne capture-clipboard --distill   # LLM extracts multiple facts
```

### Memory recall

```bash
# Recall anything — searches all three layers, cited answer
anamne recall "why did we switch from MySQL?"
anamne recall "payment architecture" --stream  # stream tokens as they arrive

# Ask a question scoped to one layer (faster, no LLM for scratchpad/working)
anamne ask "postgres preference" --layer scratchpad
anamne ask "current focus" --layer working
anamne ask "deployment decisions" --layer episodic --stream

# Direct scratchpad search — fast, ACT-R ranked, no API key needed
anamne search postgres
anamne search "python preference" --limit 5 --tag backend
anamne search deploy --pinned       # only pinned facts

# Pure-semantic search (embeddings only, no substring match)
anamne similar "why we picked our database"
anamne similar "deployment philosophy" --limit 5

# List all scratchpad facts (optionally filter by tag or pin status)
anamne facts
anamne facts --tag python --limit 10
anamne facts --pinned               # only pinned facts
anamne facts --from 2026-05-01 --to 2026-05-11   # date-range filter
anamne facts --sort activation      # sort by ACT-R score
anamne facts --json                 # machine-readable JSON output

# Show most recently added facts (quick journal-style review)
anamne recent
anamne recent --limit 20 --tag journal

# Show active working memory
anamne working

# Add a session note to working memory (expires in 60 min by default)
anamne working "currently debugging the auth middleware"
anamne working "debugging login flow" --ttl 120  # 2 hours

# Search working memory notes
anamne search-working "debug"

# Promote a working note into a permanent scratchpad fact
anamne promote <working-id>
anamne promote <working-id> --tag architecture --tag postgres

# LLM-generated 'about me' summary from pinned + top facts
anamne profile
```

### Fact management

```bash
# Show full details + ACT-R activation score for a fact
anamne info <memory-id>

# Edit a fact's content (old version preserved in history)
anamne edit <memory-id> "Corrected or updated text"

# View the full change history of a fact
anamne history <memory-id>

# Add/remove/replace tags
anamne tag <memory-id> --add python --add backend
anamne tag <memory-id> --remove deprecated
anamne tag <memory-id> --set python --set testing   # replaces all tags

# Pin a fact - protect it from auto-consolidation forever
anamne pin <memory-id>
anamne unpin <memory-id>    # remove protection

# Ask the LLM which top-accessed facts deserve to be pinned
anamne suggest-pins                # preview suggestions
anamne suggest-pins --apply        # apply them automatically

# Apply a tag to multiple facts at once (useful after an import batch)
anamne bulk-tag architecture abc123 def456 ghi789

# Find facts semantically similar to a given fact (ChromaDB neighbors)
anamne related <memory-id>
anamne related <memory-id> --limit 5
anamne related <memory-id> --tag python   # tag-filtered neighbors

# Rename a tag across every fact (e.g. fix typos)
anamne tag-rename pyhton python

# Strip a tag from all facts WITHOUT deleting the facts
anamne tag-clear deprecated
anamne tag-clear web-import --yes

# Delete a specific fact
anamne forget <memory-id>
```

### Reminders

```bash
# Store a time-bound reminder in working memory (auto-expires)
anamne reminder "check build logs"              # expires in 60 min (default)
anamne reminder "review PR #42" --in 30        # expires in 30 minutes
anamne reminder "standup" --at 09:30           # expires at 09:30 today
```

### Memory maintenance

```bash
# Merge redundant/duplicate facts using LLM (sleep-phase consolidation)
anamne consolidate --dry-run   # preview first
anamne consolidate             # apply

# Bulk index a git repo — extracts architectural decisions from commit history
anamne index ./my-project
anamne index ./my-project --adr-dir ./docs/adr

# Incremental re-index — only new commits since last run (saves API calls)
anamne sync ./my-project

# Background consolidation daemon — periodically merges redundant facts
anamne watch                   # runs every hour
anamne watch --interval 1800   # every 30 minutes

# Watch git repos and auto-sync new commits as they land
anamne watch-repos ./my-project
anamne watch-repos ./frontend ./backend --interval 120   # check every 2 min

# Daily/weekly memory recap — LLM summary of activity
anamne recap                       # what happened today
anamne recap --days 7              # last week
anamne recap --no-llm              # raw dump without LLM

# Export all memories to JSON or Markdown (for backup / migration)
anamne export --output backup.json
anamne export --format markdown --output memories.md
anamne export --tag python --output python-facts.json  # tag-scoped
anamne export --since 2026-05-01 --output delta.json   # incremental backup

# Bulk-delete all facts with a specific tag
anamne forget-tag web-import             # preview list then confirm
anamne forget-tag docs.example.com --yes # skip confirmation

# Wipe an entire memory layer (irreversible)
anamne clear scratchpad        # or: working | episodic | all

# Find and remove exact-text duplicate facts (no LLM)
anamne dedupe             # preview
anamne dedupe --yes       # auto-delete duplicates

# Show memory stats
anamne status

# Detailed analytics: most-accessed facts, creation histogram, ACT-R summary, tag breakdown
anamne stats

# Tag distribution + co-occurrence analysis
anamne tag-stats
anamne tag-stats --top 30 --history   # include monthly growth per tag

# Just list all distinct tags with counts
anamne tags
anamne tags --sort name --limit 200

# Chronological view of memory activity over time
anamne timeline
anamne timeline --days 7 --tag python
```

### Backup, restore, and sharing

```bash
# Export all memories to JSON (for backup or sharing)
anamne export --output backup.json
anamne export --format markdown --output memories.md

# Import from another ANAMNE export (restore backup, or merge a teammate's facts)
anamne import-memory backup.json
anamne import-memory team-shared-facts.json --dry-run   # preview first
anamne import-memory old-machine.json --no-working      # skip working memory
```

### Diagnostics

```bash
# Run a full health check — API keys, SQLite, ChromaDB, model config
anamne doctor
```

### Local web dashboard

```bash
# Open the memory browser in your default browser
anamne ui                      # http://127.0.0.1:8765
anamne ui --port 9000 --no-browser
```

The dashboard shows all scratchpad facts with tag/text filtering, ACT-R activation scores,
a live search tab, working memory, indexed repos, a per-fact history modal, and a
**Fact Graph** tab — a force-directed SVG visualization of facts as nodes connected
through shared tags (bipartite layout, pure JS, no D3).

### MCP server

```bash
anamne mcp-server  # stdio transport — for Claude Code, Cursor, Cline
```

---

## MCP Integration

ANAMNE exposes **18 tools** through the MCP protocol, giving any compatible AI assistant
direct access to your memory layers:

| Tool | Layer | What it does |
|---|---|---|
| `ask_why` | All | Oracle recall — cross-layer, cited answer |
| `search_decisions` | Episodic | Raw semantic search of git/ADR decisions |
| `get_file_context` | Episodic | All decisions related to a specific file |
| `get_stats` | All | Memory layer statistics |
| `remember` | Scratchpad | Store a durable fact |
| `list_facts` | Scratchpad | List scratchpad facts |
| `forget_fact` | Scratchpad | Delete a scratchpad fact |
| `get_fact` | Scratchpad | Full detail for one fact + ACT-R score |
| `tag_fact` | Scratchpad | Add/remove/set tags on a fact |
| `update_fact` | Scratchpad | Edit fact content (old version preserved) |
| `get_fact_history` | Scratchpad | Full change log for a fact |
| `search_facts` | Scratchpad | Hybrid ranked search (substring + semantic) |
| `consolidate_facts` | Scratchpad | Merge redundant facts (ACC-style) |
| `pin_fact` | Scratchpad | Protect a fact from auto-consolidation |
| `unpin_fact` | Scratchpad | Remove consolidation protection |
| `working_memory_add` | Working | Add a session note (auto-expires) |
| `working_memory_active` | Working | Get active session context |
| `search_working_memory` | Working | Semantic search over session notes |

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
anamne import-web https://12factor.net   # distill the 12-factor manifesto
anamne recall "what have we decided about deployment?"

# Browse everything in your browser
anamne ui
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
- `capture-clipboard` uses platform-specific fallbacks; install `pyperclip` for best cross-platform support.
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
git tag v0.5.0
git push origin v0.5.0
```

One-time setup: add a Trusted Publisher at https://pypi.org/manage/account/publishing/ with:
- Repository: `venumittapalli576/anamne`
- Workflow: `publish.yml`
- Environment: `pypi`

---

## License

MIT. Open source. Bring your own key. Zero telemetry.
