# Changelog

All notable changes to ANAMNE are documented here.

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
