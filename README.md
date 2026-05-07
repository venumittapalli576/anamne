# PROVENANCE

> A CLI tool that turns your git history into an answerable knowledge base.
> Ask why architectural decisions were made. Get cited answers.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

---

## What It Does

Read your git history. Extract architectural decisions from commit messages and ADR files using an LLM. Store them in a local knowledge base. Ask questions in plain English and get answers with citations.

```bash
provenance ask "why was Redis added?"
# → Load testing showed /products timing out at 200 concurrent users.
#   Redis added with 5-min TTL, reducing p99 latency from 4200ms to 180ms.
#   Source: commit a3f9c12 by alice (2024-03-15)
```

That's the whole tool. One question, one answer, with sources.

---

## What It Doesn't Do

Be honest with yourself before installing this:

- **It's only as good as your commit messages.** If your team commits "wip" and "fix bug," there's nothing to extract. Garbage in, garbage out.
- **It doesn't read your code.** Cursor and Copilot do that. PROVENANCE only reads the history of *why* the code changed.
- **It's not a replacement for ADRs.** It complements them. If you write good ADRs, PROVENANCE indexes those too.
- **It costs money to index large repos** (unless you use the free tier — see Setup).

---

## Setup

### One-command install

```bash
pip install provenance-ai
provenance init
```

`provenance init` walks you through everything: picks a model based on what you have available, indexes your current repo, and runs a sample query to confirm it works.

### Model options

| Model | Cost | Quality | Setup |
|---|---|---|---|
| **Gemini 2.5 Flash** (default) | Free tier | Good | Google account → free key |
| Claude Sonnet 4.6 | ~$0.003/commit | Best | Anthropic API key |
| Ollama (llama3.2) | Free, offline | Roadmap | Not yet implemented |

If you have no key set, `provenance init` defaults to Gemini's free tier.

---

## Commands

```bash
provenance init                       # interactive setup
provenance index <repo>               # read git history into knowledge base
provenance ask "your question"        # answer a WHY question
provenance status                     # show indexed repos and stats
provenance mcp-server                 # run as MCP server for Cursor/Claude Code
```

---

## MCP Integration

PROVENANCE runs as an MCP server, so it plugs into Cursor, Claude Code, and any MCP-compatible AI tool. When you're editing code, the AI can ask PROVENANCE for the WHY context automatically.

**Claude Code** (`.claude/settings.json`):
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

**Cursor** (Settings > MCP):
```json
{ "command": "provenance mcp-server" }
```

Tools exposed:
- `ask_why(question)` — answer questions about decisions
- `search_decisions(query, limit)` — semantic search over decisions
- `get_file_context(file_path)` — decisions touching a file
- `get_stats()` — index status

---

## Demo

Want to see it work without indexing your real repo?

```bash
python scripts/create_test_repo.py    # creates ./test-repo with 10 fake commits
provenance index ./test-repo
provenance ask "why was Redis added?"
provenance ask "why was JWT replaced with opaque tokens?"
```

---

## How It Works

```
git history     →  Historian Agent  →  decisions stored in
+ ADR files        (LLM extracts        SQLite + ChromaDB
                    structured WHYs)    (local, ~/.provenance/)

your question   →  Oracle Agent     →  cited answer
                   (semantic search +
                    LLM with context)
```

Storage is local. Nothing leaves your machine except prompts to your chosen LLM. Bring your own key. Zero telemetry.

---

## Project Status

This is a personal open-source project. It works. It's MIT licensed. PRs welcome.

**What's built (v0.1.0):**
- CLI with `init`, `index`, `ask`, `status`, `mcp-server`
- Historian Agent (git → decisions)
- Oracle Agent (WHY answers with citations)
- MCP server (Cursor/Claude Code compatible)
- Local SQLite + ChromaDB store

**What's planned (no commitment on timing):**
- Better commit message filtering (skip trivial changes)
- ADR file auto-detection (MADR, RFC formats)
- VS Code extension (as a thin wrapper)
- Simple web UI for browsing decisions

**What's not planned:**
- Enterprise features
- Compliance modes
- Anything that requires a paid tier

See [ROADMAP.md](ROADMAP.md).

---

## Limitations to Know About

1. **Commit message quality is the ceiling.** This tool can't invent context that isn't there.
2. **Indexing a 5,000-commit repo takes 10-30 minutes** and may cost a few dollars on Claude (free on Gemini's tier within rate limits).
3. **Local Ollama is noticeably worse** than Claude or Gemini for extraction quality.
4. **MCP support is required** for the editor integration. Most editors don't support MCP yet — Cursor and Claude Code do.

---

## Install From Source

```bash
git clone https://github.com/venumittapalli576/provenance
cd provenance
pip install -e .
```

---

## License

MIT.
