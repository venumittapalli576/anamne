# Changelog

All notable changes to ANAMNE are documented here.

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
