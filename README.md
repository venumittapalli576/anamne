# PROVENANCE

> A local-first, brain-inspired memory layer for everyone who uses Claude, Cursor, ChatGPT, or any MCP-compatible AI tool.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

---

## What It Does

AI tools forget you between sessions. Every time you open a new chat with Claude or Cursor, you re-explain who you are, what you're working on, what you've already decided.

PROVENANCE is a memory layer that sits on **your** machine, captures the things worth remembering across all your AI conversations and your code history, and feeds them back into any AI tool through MCP.

```bash
# Capture a fact
provenance remember "I'm a vegetarian who's allergic to peanuts"

# Recall context for any topic
provenance recall "what dietary restrictions do I have?"

# Or let it index your git history automatically
provenance index ./my-repo
```

When you next open Claude or Cursor, the AI already knows what matters — without you re-typing it.

---

## Why This Exists

Recent benchmarks: top models drop accuracy from 99% to 30% as conversations grow long. Even 1M-token context windows lose track of what mattered three turns ago.

The fix isn't bigger context windows. It's **structured memory** — the way human brains do it.

PROVENANCE implements a **brain-inspired three-layer memory architecture** drawn from 2026 research (LIGHT, ACT-R, ACC):

| Layer | Brain analog | What it stores |
|---|---|---|
| **Episodic** | Long-term hippocampal index | Full record of past conversations and code decisions |
| **Working** | Prefrontal cortex | What you're focused on right this session |
| **Scratchpad** | Semantic memory | Distilled facts ("I prefer Python", "we use Postgres") |

Each layer has its own retrieval policy and decay rules. Combined, they let any AI tool feel like it remembers you across sessions, devices, and even across different AI tools.

---

## Setup

```bash
pip install provenance-ai
provenance init
```

`provenance init` walks you through everything. Picks a model based on what API keys you have, creates the local memory store, indexes your current repo if any.

| Model | Cost | Quality | Setup |
|---|---|---|---|
| **Gemini 2.5 Flash Lite** (default) | Free tier | Good | Google login → free key |
| Claude Sonnet 4.6 | ~$0.003/commit | Best | Anthropic API key |
| Ollama | Free, offline | Roadmap | Not yet implemented |

---

## Commands

```bash
provenance init                       # interactive setup
provenance remember "fact or note"    # add to scratchpad memory
provenance recall "your question"     # cross-layer recall, cited
provenance index <repo>               # bulk-import git history into episodic memory
provenance status                     # show memory stats
provenance mcp-server                 # run as MCP server for AI tools
```

---

## MCP Integration — Memory Layer for Any AI Tool

PROVENANCE runs as an MCP server, exposing memory tools to Claude, Cursor, Cline, and any MCP-compatible AI:

| Tool | What it does |
|---|---|
| `recall(question)` | Cross-layer memory search with citations |
| `remember(fact)` | Add a fact to scratchpad memory |
| `working_context()` | What you've been working on this session |
| `episodic_search(query)` | Long-term memory retrieval |
| `forget(memory_id)` | Explicit deletion (matches brain decay) |

**Claude Code** (`~/.claude/claude_desktop_config.json` or `~/.claude.json`):
```json
{
  "mcpServers": {
    "provenance": {
      "command": "provenance",
      "args": ["mcp-server"],
      "cwd": "/path/to/your/.provenance/data"
    }
  }
}
```

**Cursor** (Settings > MCP):
```json
{ "command": "provenance mcp-server" }
```

---

## Why Local-First

- Your memory stays on your machine. Nothing goes to a vendor server.
- Your API keys stay in your `.env`. No middleman billing.
- Your data is portable — SQLite + a folder of files. Take it anywhere.
- Open source under MIT. No vendor lock-in.

This is the opposite of cloud memory products like Mem0 or Supermemory, which target app developers and require their backend. PROVENANCE is for individual humans using AI tools.

---

## Honest Limitations

- Output quality depends on how clearly you capture memories. Garbage in, garbage out.
- Indexing a large repo can be slow and cost a few dollars on paid LLM APIs (free on Gemini's tier within rate limits).
- MCP integration only works in editors that support MCP (Cursor, Claude Code, Cline, a few others).
- This is a personal project. Not production infrastructure.
- Brain-inspired architecture is approximate — neuroscience is hard, this is a useful metaphor not a model of the actual brain.

---

## Inspired By Recent Research

This isn't a from-scratch design. PROVENANCE implements ideas from:

- **LIGHT** — three-layer memory framework ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246))
- **ACT-R-Inspired Memory** — temporal decay + activation
- **Agent Cognitive Compressor** — bounded compressed cognitive state
- **Hippocampal indexing theory** — episodic memory stores compressed neocortical patterns

---

## Demo

```bash
python scripts/create_test_repo.py
provenance index ./test-repo
provenance recall "why was Redis added?"
provenance remember "always use 2-space indentation in this project"
provenance recall "what's our indentation style?"
```

---

## Status

- v0.1.x — git-history capture and recall (works)
- v0.2.x — explicit `remember` and `working_context` (in progress)
- v0.3.x — multi-source capture (clipboard, browser, AI conversations)

---

## License

MIT. Open source. Bring your own key. Zero telemetry.
