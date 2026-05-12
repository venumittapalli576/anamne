# ANAMNE — Stable Surface (v1.0)

This document lists the commands ANAMNE commits to maintaining for the v1.x
series. Commands not on this list still work but are marked `hidden=True` —
they are reserved for power users and may change or be removed without a
major version bump.

If you script against ANAMNE, build on these commands only.

---

## Setup & health

| Command | Purpose |
|---|---|
| `init` | Interactive setup wizard — picks a model, writes `.env`, optionally indexes a repo |
| `doctor` | Diagnose API keys, SQLite/ChromaDB sync, model config |

## Memory capture

| Command | Purpose |
|---|---|
| `remember "<fact>"` | Store a durable fact in scratchpad memory |
| `journal "<entry>"` | Timestamped journal entry (auto-tagged `journal`) |
| `import-web <url>` | Scrape a web page and distill key facts |
| `import-chat <file>` | Extract facts from an exported AI conversation |
| `capture-clipboard` | Save the current clipboard contents as a fact |
| `working "<note>"` | Add a short-lived session note (auto-expires) |

## Memory recall

| Command | Purpose |
|---|---|
| `ask "<question>"` | Cross-layer recall with citations (Oracle, uses LLM) |
| `search "<query>"` | Direct ranked search across scratchpad — no LLM needed |
| `search-working "<query>"` | Search active working-memory notes |

## Inspect

| Command | Purpose |
|---|---|
| `facts` | List scratchpad facts (`--tag`, `--pinned`, `--sort`, `--from/--to`) |
| `info <id>` | Full details + ACT-R activation for one fact |
| `history <id>` | Audit log entries for one fact |
| `tags` | List every distinct tag with its fact count |
| `status` | Quick stats summary (counts per layer) |
| `stats` | Deeper analytics (top-accessed, creation rate, tag breakdown) |

## Manage facts

| Command | Purpose |
|---|---|
| `edit <id> "<new text>"` | Update fact content (old version preserved in history) |
| `tag <id> --add/--remove/--set` | Manage tags on a fact |
| `tag-rename <old> <new>` | Bulk rename a tag across every fact |
| `forget-tag <tag>` | Bulk-delete every fact with a tag |
| `pin <id>` / `unpin <id>` | Protect a fact from auto-consolidation |
| `forget <id>` | Delete a specific fact |
| `prune --older-than YYYY-MM-DD` | Bulk-prune stale facts (preserves pinned) |
| `clear <layer>` | Wipe an entire memory layer |
| `dedupe` | Exact-text duplicate removal (no LLM) |
| `consolidate` | LLM-driven merge of redundant facts |

## Episodic / git

| Command | Purpose |
|---|---|
| `index <repo>` | Build the WHY knowledge graph from git history |
| `sync <repo>` | Incremental re-index — only new commits |
| `watch` | Periodic auto-consolidation daemon |

## Backup & sharing

| Command | Purpose |
|---|---|
| `export` | JSON or Markdown dump (`--tag`, `--since`, `--signed`, `--encrypt`) |
| `import-memory <file>` | Restore from an `export` file (`--verify`, `--decrypt`) |
| `backup` | One-shot timestamped JSON backup with rotation (`--keep N`) |

## Interfaces

| Command | Purpose |
|---|---|
| `mcp-server` | Start the MCP server (stdio) for Claude Code / Cursor / Cline |
| `mcp-config --client <name>` | Print or `--apply` a paste-ready MCP config snippet |
| `tools` | List the MCP tools the server would expose |
| `shell` | Interactive REPL (tab completion + persistent history) |
| `ui` | Local web dashboard at `http://127.0.0.1:8765` |

---

## Hidden commands (kept for power users, not part of the stable surface)

These still work — run them by name — but they are not on the menu, may
overlap with canonical commands, and could change or be removed in any
minor release.

**Search variants:** `recall`, `similar`, `related`, `search-all`

**Tag variants:** `bulk-tag`, `tag-clear`, `tag-stats`, `tag-search`

**Display variants:** `recent`, `quote`, `mark`, `random`, `fact-of-the-day`,
`snapshot`, `profile`, `recap`, `timeline`, `tail`, `reminder`, `stash`

**LLM novelties:** `quiz`, `template`, `suggest-pins`, `suggest-tags`

**Fact ops:** `diff`, `merge`, `promote`

**Advanced / experimental:** `notebook`, `sync-cloud`, `key-rotate`,
`audit-log`, `watch-repos`, `tool-call`

---

## MCP tool surface (21 tools)

The MCP tool list is also stable for v1.x. See `anamne tools` for the live
list with descriptions, or `anamne tools --schema <name>` for parameters.

## Stability promise

For the v1.x series:

- Visible commands keep their current names, primary arguments, and exit codes.
- New flags may be added; existing flags will not be removed or repurposed.
- New visible commands may be added; existing visible commands will not be
  removed (deprecation requires a v2.x major).
- Hidden commands have **no** stability promise.
- The data on disk (`~/.anamne/`) will continue to be readable across minor
  releases.
