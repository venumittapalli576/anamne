# PROVENANCE

> **The living memory of why your code exists.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

---

## What Is This?

Every codebase accumulates two kinds of debt:
- **Technical debt** — messy code
- **Knowledge debt** — no one knows *why* the code exists

Cursor and Copilot can read your code. **PROVENANCE captures the WHY** — the reasoning behind every architectural decision, preserved forever and queryable by any AI tool.

```bash
provenance ask "why was Redis added?"
# → "Load testing showed /products timing out at 200 concurrent users.
#    Redis was added with a 5-min TTL, reducing p99 latency from 4200ms to 180ms.
#    Source: commit a3f9c12 by @alice (2024-03-15)"

provenance ask "why was JWT replaced?"
# → "Security audit SEC-1234 found JWTs in localStorage are XSS-vulnerable.
#    Switched to opaque tokens in httpOnly cookies. Redis required for token store."
```

---

## Why PROVENANCE Wins Against Cursor / Copilot / OpenClaw

| Feature | Cursor | Copilot | OpenClaw | **PROVENANCE** |
|---|---|---|---|---|
| Reads your code | Yes | Yes | Yes | Yes |
| Knows *why* code exists | No | No | No | **Yes** |
| Temporal decisions (when valid) | No | No | No | **Yes** |
| Works with ANY AI tool via MCP | No | No | No | **Yes** |
| Self-hosted, zero telemetry | No | No | No | **Yes** |
| EU AI Act Article 11/12 ready | No | No | No | **Yes (Phase 3)** |
| Vibe Debt Scanner | No | No | No | **Yes (Phase 3)** |
| Model-agnostic (Claude/Gemini/Ollama) | No | No | No | **Yes** |

---

## Quick Start

```bash
# 1. Install
pip install provenance-ai

# 2. Add your API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# 3. Index your repo (reads git history, extracts decisions via Claude)
provenance index /path/to/your/repo

# 4. Ask anything
provenance ask "why was Redis added?"
provenance ask "why is authentication done with opaque tokens?"
provenance ask "why was PostgreSQL chosen over MySQL?"

# 5. Check status
provenance status
```

---

## MCP Integration — Works in Cursor, Claude Code, any MCP client

Add to **Claude Code** (`.claude/settings.json`):
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

Add to **Cursor** (Settings > MCP):
```json
{ "command": "provenance mcp-server" }
```

MCP tools exposed:
- `ask_why(question)` — answer WHY questions about any decision
- `search_decisions(query, limit)` — raw semantic search over decisions
- `get_file_context(file_path)` — all decisions related to a specific file
- `get_stats()` — knowledge base statistics

---

## Architecture

```
+-----------------------------------------------------+
|                  PROVENANCE                         |
+------------------+----------------------------------+
|   Data Sources   |   Agents                        |
|   -----------    |   ------                        |
|   Git history    |   Historian  -> indexes repo    |
|   ADR files      |   Oracle     -> answers WHY     |
|   (Phase 2+)     |   Sentinel   -> reviews PRs     |
|   Jira/Linear    |   Mentor     -> onboards devs   |
|   Slack exports  |   Builder    -> WHY-aware code  |
|                  |   Prophet    -> detects staleness|
+------------------+----------------------------------+
|   Storage                                           |
|   SQLite (temporal/relational) + ChromaDB (semantic)|
+-----------------------------------------------------+
|   Interfaces                                        |
|   CLI (Typer+Rich) | MCP Server | Web Dashboard     |
+-----------------------------------------------------+
```

---

## Project Structure

```
provenance/
├── provenance/
│   ├── agents/
│   │   ├── historian.py      # Git -> knowledge graph
│   │   └── oracle.py         # WHY question answering
│   ├── cli/
│   │   └── main.py           # Typer CLI (init/index/ask/status/mcp)
│   ├── mcp/
│   │   └── server.py         # FastMCP server for Cursor/Claude Code
│   ├── store/
│   │   └── graph.py          # SQLite + ChromaDB dual store
│   ├── config.py             # Pydantic settings (ANTHROPIC_API_KEY etc.)
│   └── models.py             # Decision dataclass (bi-temporal)
├── scripts/
│   └── create_test_repo.py   # Demo repo with 10 realistic commits
├── pyproject.toml
├── .env.example
└── ROADMAP.md
```

---

## Configuration

Copy `.env.example` to `.env`:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional overrides
MODEL=claude-sonnet-4-6          # or claude-opus-4-5, gemini-...
DATA_DIR=~/.provenance            # where to store the knowledge base
```

---

## Demo — Try It Now

```bash
# Create a realistic test repo (10 commits with real architectural decisions)
python scripts/create_test_repo.py

# Index it
provenance index ./test-repo

# Ask questions
provenance ask "why was Redis added?"
provenance ask "why was JWT replaced with opaque tokens?"
provenance ask "why was Elasticsearch chosen over PostgreSQL search?"
provenance ask "why was Stripe chosen over Braintree?"
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the detailed plan.

**Phase 0 — Core (Complete)**
- Decision model + bi-temporal store (SQLite + ChromaDB)
- Historian Agent (git -> knowledge graph)
- Oracle Agent (WHY answers)
- FastMCP server (Cursor/Claude Code integration)
- Typer+Rich CLI

**Phase 1 — Integrations (Next)**
- ADR file indexing (already scaffolded)
- GitHub PR context ingestion
- Jira / Linear ticket ingestion
- Slack export ingestion

**Phase 2 — More Agents**
- Sentinel Agent: PR review with decision context
- Mentor Agent: onboarding guided by decision history
- Builder Agent: WHY-aware code generation
- Prophet Agent: staleness detection and alerts

**Phase 3 — Enterprise**
- Vibe Debt Scanner: tracks AI-generated code accumulation
- EU AI Act Compliance Mode: Article 11 docs + Article 12 audit logs
- Web Dashboard (FastAPI + HTMX)
- Docker Compose deployment
- Gemini / Ollama / OpenAI-compatible model support

---

## Contributing

PRs welcome. See [ROADMAP.md](ROADMAP.md) for what's planned.

```bash
git clone https://github.com/venumittapalli576/provenance
cd provenance
pip install -e ".[dev]"
```

---

## License

MIT — free to use, fork, and build on. Zero telemetry. Bring your own key.
