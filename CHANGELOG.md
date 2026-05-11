# Changelog

All notable changes to ANAMNE are documented here.

---

## [0.6.1] — 2026-05-11

### Fixed
- **Windows cp1252 UnicodeEncodeError** — replaced all non-ASCII characters in CLI
  output strings (em dashes `—`, ellipsis `…`, en dashes `–`, arrow `→`, and
  banner box-drawing chars) with ASCII equivalents. All Rich `console.print()` output
  now works on Windows legacy terminals (cp1252 / PowerShell / cmd.exe).

---

## [0.6.0] — 2026-05-11

### Added — Phase 6

**`anamne import-memory`** — restore from backup / share facts with teammates
- `anamne import-memory <file.json> [--dry-run] [--no-facts] [--no-working] [--allow-dupes]`
- Reads a JSON file produced by `anamne export`
- Re-inserts scratchpad facts and working-memory notes into the current store
- Deduplicates by exact text match by default (`--skip-dupes` on by default)
- Episodic decisions are not imported (they are repo-specific; re-index with `anamne index`)
- Shows per-fact preview, skipped duplicates, and a final summary

**`anamne doctor`** — self-diagnosis and health check
- Checks API keys, data directory, SQLite accessibility, ChromaDB sync status
- Reports memory layer counts (facts / decisions / working)
- Highlights the active model
- Lists actionable issues with suggested fixes
- Zero external calls — works without an API key

### Tests
- 66 tests total (was 63), all passing
- New: 3 tests for import-memory dedup logic and working-memory search integration

---

## [0.5.0] — 2026-05-11

### Added — Phase 5

**`anamne import-web`**
- New CLI command: `anamne import-web <url> [--limit N] [--dry-run] [--tag TAG]`
- Fetches the URL with httpx, strips HTML using Python stdlib `html.parser` (zero new deps)
- LLM distils up to N durable facts from the page content
- Auto-tags with domain name + `web-import`; extra `--tag` flags apply
- Smart HTML stripping skips `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`

**Working memory semantic search**
- `working_add()` now embeds notes into a ChromaDB `working_memory` collection
- `store.search_working(query, limit)` — hybrid: substring + semantic, expired-notes-aware
- New CLI command: `anamne search-working <query>`
- New MCP tool: `search_working_memory(query, limit)` (16 MCP tools total)
- `working_active()` / `working_clear()` / `clear_working()` all prune ChromaDB in sync

**README overhaul**
- All commands documented including `edit`, `history`, `ui`, `import-web`, `search-working`, `info`, `tag`, `clear`
- MCP table updated to 16 tools
- Added web dashboard section
- Quick demo includes `import-web` example

**CI: Node.js 24 opt-in**
- Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` to both `ci.yml` and `publish.yml`
- Eliminates Node.js 20 deprecation warning ahead of June 2, 2026 deadline

### Tests
- 63 tests total (was 60), all passing
- New: 3 working-memory search tests (substring, empty, expired-filtered)

---

## [0.4.0] — 2026-05-11

### Added — Phase 4 Polish

**Fact versioning** (full auditability of scratchpad changes)
- New `fact_history` SQL table — immutable log of every create, edit, tag change, deletion, and merge
- `store.get_fact_history(fact_id)` — return full history for a fact, newest first
- `store.update_fact_content(mem_id, new_content)` — edit fact text; old version archived in history
- `store.remember()` now records `created` event on write
- `store.update_fact_tags()` now records `tags_updated` event
- `store.forget_fact()` now records `forgotten` tombstone (or `merged_into` when called by consolidation)
- Consolidation wires `merged_into → surviving_id` so you can trace what was merged where
- New MCP tool: `update_fact(memory_id, content)` — edit fact content via MCP
- New MCP tool: `get_fact_history(memory_id)` — retrieve audit trail via MCP

**Local web dashboard** (`anamne ui`)
- New CLI command: `anamne ui [--port PORT] [--no-browser]`
- Zero-dependency local HTTP server (Python stdlib only — no Flask, no FastAPI)
- Self-contained single-page app with dark theme matching GitHub's palette
- **Scratchpad** tab: browse all facts, filter by text/tag, see ACT-R scores, click for history modal
- **Search** tab: live hybrid search (substring + semantic + ACT-R ranked)
- **Working Memory** tab: active session notes with expiry times
- **Repos** tab: list all indexed repositories
- History modal: full change log per fact with color-coded change types

**New CLI commands**
- `anamne edit <id> "<new text>"` — update fact content (history preserved)
- `anamne history <id>` — show full change history as a rich table

### Tests
- 60 tests total (was 52), all passing
- New: 8 fact-versioning tests covering create / edit / tag / forget / merge / history order

---

## [0.3.1] — 2026-05-11

### Added
- `anamne --version` / `anamne -V` — print version and exit

### Fixed
- `SECURITY.md`, issue templates, and PR template added for open-source hygiene
- PyPI + CI badges in README
- `.gitattributes` for consistent cross-platform line endings

---

## [0.3.0] — 2026-05-10

### Added — Phase 3 memory upgrades

**Semantic scratchpad search**
- Facts are now embedded into a dedicated ChromaDB `scratchpad` collection on write
- `search_facts_semantic()` — embedding-based search; finds conceptually related facts
  even when exact keywords don't match (e.g. "database" finds "PostgreSQL" facts)
- `search_facts_ranked()` now merges substring + semantic candidates, deduplicates,
  then re-ranks by ACT-R activation — best of both retrieval strategies
- One-time migration: existing facts are back-filled into ChromaDB on first startup
- `forget_fact()` now also deletes from ChromaDB scratchpad collection

**Incremental indexing**
- New `indexed_commits` SQL table tracks which commits have already been processed
- `is_commit_indexed()`, `mark_commit_indexed()`, `indexed_commit_count()` on store
- `HistorianAgent.index_repo(incremental=True)` skips already-indexed commits
- New CLI command: `anamne sync <repo>` — re-indexes only new commits,
  saving API calls when you run it after `git pull` or `git commit`

**Auto-consolidation daemon**
- New CLI command: `anamne watch` — runs `consolidate` on a configurable schedule
  (default: every 3600s). Background memory maintenance, analog of sleep-phase
  consolidation in cognitive science. Press Ctrl+C to stop.

**New CLI commands** (search, export, capture-clipboard added in this release too)
- `anamne search <query>` — direct ACT-R-ranked scratchpad search, no API key needed
- `anamne export` — dump all memories to JSON or Markdown for backup/migration
- `anamne capture-clipboard` — read clipboard and save as scratchpad fact

### Fixed
- `status` command: removed dead `ollama` reference in API key check
- `recall` and MCP `search_facts`: upgraded to `search_facts_ranked()` (was unranked)

### Tests
- 41 tests total (was 31 → 34 → 41), all passing
- New: semantic search (3), incremental indexing (4), list_all_decisions (3)

---

## [0.2.0] — 2026-05-10

### Changed (breaking)
- **Renamed**: project `provenance` → `anamne` (CLI command, package, data dir `~/.anamne`)
- **Removed**: Ollama support (local models too weak for structured JSON extraction tasks)
- **Removed**: dead FastAPI/uvicorn/jinja2 dependencies

### Added — Memory architecture (LIGHT + ACC frameworks)
- **Three-layer memory** following the LIGHT framework (arXiv 2510.27246):
  - *Episodic* — long-term decisions from git history (ChromaDB semantic search)
  - *Scratchpad* — durable user-stated facts (SQLite, full-text search)
  - *Working memory* — short-lived session context with TTL auto-expiry
- **ACT-R real decay formula**: `A_i = ln(Σ t_j^-d)` where `t_j` = seconds since retrieval `j`
  - New `retrieval_log` SQL table — every fact access is timestamped
  - `activation_score()` — computes true ACT-R base-level activation
  - `search_facts_ranked()` — re-ranks search results by ACT-R activation
- **ACC bounded context compression**: top-3 episodic results verbatim, tail LLM-compressed
- **Fact consolidation** (`anamne consolidate`): Jaccard keyword clustering + LLM merge
- **Layer-conflict priority**: scratchpad > working > episodic (per LIGHT design)
- **Staleness flags**: episodic items with `valid_until` in the past show `[POTENTIALLY STALE]`

### Added — CLI commands
| Command | Description |
|---|---|
| `anamne journal` | Timestamped scratchpad entry with auto `journal` tag |
| `anamne import-chat` | Extract durable facts from exported Claude / ChatGPT JSON |
| `anamne consolidate` | Merge redundant facts (Jaccard overlap + LLM) |
| `anamne search` | Direct scratchpad search, ACT-R ranked, no API key needed |
| `anamne export` | Backup all memories to JSON or Markdown |
| `anamne capture-clipboard` | Save clipboard text as a scratchpad fact |
| `anamne recall` | Cross-layer recall (upgraded to use ACT-R ranking) |

### Added — MCP tools (11 total)
| Tool | Layer |
|---|---|
| `ask_why` | Cross-layer (Oracle) |
| `search_decisions` | Episodic |
| `get_file_context` | Episodic |
| `get_stats` | All |
| `remember` | Scratchpad |
| `list_facts` | Scratchpad |
| `forget_fact` | Scratchpad |
| `search_facts` | Scratchpad (ACT-R ranked) |
| `consolidate_facts` | Scratchpad |
| `working_memory_add` | Working |
| `working_memory_active` | Working |

### Added — Infrastructure
- **Test suite** (31 tests, 100% pass):
  - `tests/test_models.py` — Decision model, staleness, serialisation
  - `tests/test_store.py` — all three memory layers + ACT-R activation
  - `tests/test_clustering.py` — `_cluster_by_overlap` threshold behaviour
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — runs on every push/PR
- **pyproject.toml**: authors, keywords, classifiers, project URLs, dev extras
- **LICENSE**: MIT, copyright Venu Mittapalli
- **BLOG_POST.md**: origin story and technical deep-dive

### Fixed
- `status` command: removed dead `ollama` reference in API key check
- `recall` command: now uses `search_facts_ranked()` (was unranked)
- MCP `search_facts` tool: now uses `search_facts_ranked()` (was unranked)
- README, ROADMAP: all `provenance` references updated to `anamne`

---

## [0.1.0] — 2026-04 (internal)

First working version under the name `provenance`.

- `Decision` data model with bi-temporal fields
- SQLite + ChromaDB dual store
- Historian Agent — git history extraction via LLM
- Oracle Agent — recall with citations
- FastMCP server with 4 tools
- CLI: `init`, `index`, `ask`, `status`, `mcp-server`
- Claude + Gemini multi-model LLM client
