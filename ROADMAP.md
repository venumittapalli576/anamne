# ANAMNE — Roadmap

A local-first, brain-inspired memory layer for AI users. Personal open-source project. MIT.

---

## What's Built (v0.1.0)

- `Decision`/`Memory` data model with bi-temporal fields (created_at, valid_until)
- SQLite + ChromaDB dual store
- Historian Agent — captures memories from git history via LLM
- Oracle Agent — recalls memories with citations
- FastMCP server with 4 tools (`ask_why`, `search_decisions`, `get_file_context`, `get_stats`)
- CLI with `init`, `index`, `ask`, `status`, `mcp-server`
- Working multi-model LLM client (Claude + Gemini)
- One-command setup via `anamne init`

---

## What's Built (v0.2.0)

**Pivot:** brain-inspired personal memory layer for AI users, grounded in two 2026 research papers.

| Feature | Source | Status |
|---|---|---|
| Three-layer memory (episodic/scratchpad/working) | LIGHT (arXiv 2510.27246) | ✅ |
| Cross-layer recall with citation | LIGHT retrieval design | ✅ |
| Layer-conflict resolution priority | LIGHT prompt design | ✅ |
| ACT-R real decay formula (`A_i = ln(Σ t_j^-d)`) | ACT-R (Anderson & Lebiere 1998) | ✅ |
| `retrieval_log` table — every access timestamped | ACT-R implementation | ✅ |
| `search_facts_ranked()` — re-rank by activation | ACT-R + LIGHT | ✅ |
| LLM-based fact distillation (`remember --distill`) | LIGHT key-value extraction | ✅ |
| Working memory with TTL decay | Beyond LIGHT | ✅ |
| Bounded context compression (top-K verbatim + tail summary) | Agent Cognitive Compressor | ✅ |
| Scratchpad consolidation (`anamne consolidate`) | ACC + sleep-phase consolidation | ✅ |
| Full MCP tool surface (11 tools, all ACT-R ranked) | — | ✅ |
| `anamne journal` — timestamped quick entry | Phase 2 capture | ✅ |
| `anamne import-chat` — Claude/ChatGPT JSON extraction | Phase 2 capture | ✅ |
| `anamne search` — direct scratchpad search, no API key | Usability | ✅ |
| `anamne export` — JSON/Markdown backup | Portability | ✅ |
| `anamne capture-clipboard` — clipboard -> scratchpad | Phase 2 capture | ✅ |
| Test suite (31 tests, 100% pass) | Quality | ✅ |
| GitHub Actions CI | Quality | ✅ |

---

## Direction

Originally ANAMNE captured "WHY decisions were made" from git. Repowise (and others) already do
this well. **v0.2 pivots to a brain-inspired personal memory layer for AI users.** The architecture
maps directly onto the LIGHT memory framework and the ACC bounded-state design from 2026 research.

---

## What's Built (v0.3.0)

| Feature | Status |
|---|---|
| Semantic scratchpad search (ChromaDB `scratchpad` collection) | ✅ |
| Hybrid ranked search (substring + semantic + ACT-R activation) | ✅ |
| One-time migration of existing facts into ChromaDB | ✅ |
| Incremental indexing (`indexed_commits` table, `anamne sync`) | ✅ |
| `anamne watch` — periodic auto-consolidation daemon | ✅ |
| `anamne search` — direct ranked search, no API key | ✅ |
| `anamne export` — JSON/Markdown memory backup | ✅ |
| `anamne capture-clipboard` — clipboard -> scratchpad | ✅ |

---

## What's Built (v0.3.1)

| Feature | Status |
|---|---|
| `anamne --version` / `-V` flag | ✅ |
| SECURITY.md, issue templates, PR template | ✅ |
| PyPI + CI badges in README | ✅ |
| Trusted Publishing (zero-token PyPI releases via OIDC) | ✅ |
| `.gitattributes` for cross-platform line endings | ✅ |

---

## What's Built (v0.4.0)

| Feature | Status |
|---|---|
| `fact_history` table — immutable audit log of every scratchpad change | ✅ |
| `anamne edit <id>` — update fact content, preserving old version | ✅ |
| `anamne history <id>` — show full change log per fact | ✅ |
| MCP `update_fact` + `get_fact_history` tools (15 MCP tools total) | ✅ |
| `anamne ui` — local web dashboard (zero extra deps, dark theme) | ✅ |
| Consolidation records `merged_into` links in history | ✅ |

---

## What's Built (v0.5.0)

| Feature | Status |
|---|---|
| `anamne import-web <url>` — scrape + distill facts from any web page | ✅ |
| Working memory ChromaDB embeddings + `search_working()` | ✅ |
| `anamne search-working <query>` CLI command | ✅ |
| MCP `search_working_memory` tool (16 tools total) | ✅ |
| README fully updated (all commands, 16-tool MCP table) | ✅ |
| GitHub Actions: opt into Node.js 24 | ✅ |

---

## What's Built (v0.6.0)

| Feature | Status |
|---|---|
| `anamne import-memory <file>` — restore backup / share facts across machines | ✅ |
| `anamne doctor` — health check: API keys, SQLite, ChromaDB sync, model | ✅ |
| 66 tests, 100% passing | ✅ |

---

## What's Built (v0.7.0)

| Feature | Status |
|---|---|
| `remember --auto-tag` - LLM suggests tags automatically | ✅ |
| `anamne watch-repos` daemon - poll git repos and auto-sync on new commits | ✅ |
| Enhanced `status` with top-tags breakdown | ✅ |

---

## What's Built (v0.8.0)

| Feature | Status |
|---|---|
| `anamne import-web --crawl` - BFS site-wide crawl, same-domain link following | ✅ |
| `--max-pages` cap for crawl mode, per-page progress, global cross-page dedup | ✅ |
| Fact Graph tab in web UI - force-directed SVG, bipartite fact+tag layout | ✅ |
| `/api/graph` endpoint - returns nodes/edges JSON for vis | ✅ |
| Drag-to-reposition nodes, hover tooltips, 400-frame force simulation | ✅ |
| `anamne stats` - detailed analytics: most-accessed, creation rate, ACT-R avg | ✅ |
| Per-day facts-added histogram, oldest/newest fact, tag distribution table | ✅ |

---

## What's Built (v0.9.0)

| Feature | Status |
|---|---|
| Graph click-through: click fact node opens history modal | ✅ |
| Click vs drag detection (< 4px movement = click) | ✅ |
| `anamne reminder` - time-bound working-memory notes (`--in N` or `--at HH:MM`) | ✅ |
| `anamne forget-tag <tag>` - bulk delete all facts with a tag, with preview | ✅ |

---

## What's Built (v0.10.0)

| Feature | Status |
|---|---|
| `anamne pin <id>` - protect fact from auto-consolidation | ✅ |
| `anamne unpin <id>` - remove protection | ✅ |
| `pinned` column in scratchpad table (safe ALTER TABLE migration) | ✅ |
| `pin_fact` / `unpin_fact` MCP tools (18 total) | ✅ |
| Consolidation skips pinned facts | ✅ |
| Pin indicator in `facts`, `search`, `info`, and web UI | ✅ |
| 72 tests, all passing (+6 pin/unpin coverage) | ✅ |

---

## What's Built (v0.11.0)

| Feature | Status |
|---|---|
| `anamne recent` - show latest facts, newest first, with creation date | ✅ |
| `anamne bulk-tag <tag> <id>...` - apply a tag to multiple facts in one step | ✅ |
| `--pinned` filter on `anamne facts` and `anamne search` | ✅ |

---

## What's Built (v0.12.0)

| Feature | Status |
|---|---|
| `anamne recap` - LLM narrative of today's memory activity | ✅ |
| `--days N` lookback, `--no-llm` raw dump mode | ✅ |
| `anamne export --tag <tag>` - tag-scoped export | ✅ |
| `anamne facts --sort activation\|created` | ✅ |

---

## What's Built (v0.13.0)

| Feature | Status |
|---|---|
| `anamne recall --stream`: streaming LLM output, token-by-token | ✅ |
| `LLMClient.complete_stream()`: Anthropic + Gemini streaming generators | ✅ |
| `OracleAgent.ask_stream()`: streaming Oracle recall to terminal | ✅ |
| `anamne dedupe`: exact-text duplicate detection + bulk delete, no LLM | ✅ |
| `anamne working --extend <id>:<minutes>`: extend working note expiry | ✅ |
| Flaky ACT-R timing test fixed with explicit 10ms sleep | ✅ |

---

## What's Built (v0.14.0)

| Feature | Status |
|---|---|
| `anamne facts --from YYYY-MM-DD --to YYYY-MM-DD` - date-range filter | ✅ |
| `anamne ask --layer episodic\|scratchpad\|working` - layer-scoped queries | ✅ |
| `anamne ask --stream` - token-by-token streaming output | ✅ |
| `anamne tag-stats` - tag distribution + co-occurrence analysis | ✅ |
| `anamne tag-stats --history` - monthly facts-tagged breakdown | ✅ |

---

## What's Built (v0.15.0)

| Feature | Status |
|---|---|
| `anamne related <id>` - semantic similarity neighbors of a fact | ✅ |
| `anamne tag-rename <old> <new>` - bulk rename a tag across all facts | ✅ |
| `anamne tag-clear <tag>` - strip a tag without deleting the facts | ✅ |
| `tag_renamed` / `tag_removed` history rows | ✅ |
| 80 tests, all passing | ✅ |

---

## What's Built (v0.16.0)

| Feature | Status |
|---|---|
| `anamne timeline` - chronological memory activity (created/retrieved/events) | ✅ |
| `anamne timeline --days N --tag X` filters | ✅ |
| `anamne tags` - quick tag listing with counts (`--sort`, `--limit`) | ✅ |
| `anamne export --since YYYY-MM-DD` - incremental delta export | ✅ |

---

## What's Built (v0.17.0)

| Feature | Status |
|---|---|
| `anamne similar <text>` - pure-semantic free-text search | ✅ |
| `anamne promote <working_id>` - move working note to scratchpad | ✅ |
| `anamne profile` - LLM "about me" summary from pinned + top facts | ✅ |
| Store: `working_get`, `working_delete`, `promote_working` methods | ✅ |
| 86 tests, all passing | ✅ |

---

## What's Built (v0.18.0)

| Feature | Status |
|---|---|
| `anamne suggest-pins` - LLM picks which top-activation facts to pin | ✅ |
| `anamne suggest-pins --apply` - auto-pin the suggestions | ✅ |
| `anamne related --tag X` - tag-filtered semantic neighbors | ✅ |
| `anamne facts --json` - machine-readable JSON output | ✅ |
| Fix `profile` to unwrap `LLMResponse.text` | ✅ |

---

## What's Built (v0.19.0)

| Feature | Status |
|---|---|
| `anamne stats --json` - machine-readable analytics dump | ✅ |
| `anamne similar --tag X` - tag-filtered pure-semantic search | ✅ |
| `anamne suggest-tags <text>` - LLM tag preview without storing | ✅ |

---

## What's Built (v0.20.0)

| Feature | Status |
|---|---|
| `anamne search --json` - machine-readable search output | ✅ |
| `anamne quote <id>` - copy-paste-ready fact formatter (plain/markdown/bullet) | ✅ |
| `anamne mark <id> "note"` - free-text audit annotation in history | ✅ |
| Flaky `test_activation_formula_correctness` fixed (10ms sleep) | ✅ |

---

## What's Built (v0.21.0)

| Feature | Status |
|---|---|
| `anamne shell` - interactive REPL (no extra deps) | ✅ |
| Built-in shell commands: search, similar, remember, journal, working, ask | ✅ |
| Built-in shell commands: info, history, recent, tags, status, help, exit | ✅ |

---

## What's Built (v0.22.0)

| Feature | Status |
|---|---|
| `anamne tail` - live tail of memory events (`--interval`, `--once`) | ✅ |
| MCP `related_facts` tool | ✅ |
| MCP `promote_working` tool | ✅ |
| MCP `mark_fact` tool | ✅ |
| 21 MCP tools total | ✅ |

---

## What's Built (v0.23.0)

| Feature | Status |
|---|---|
| `anamne search-all <query>` - cross-layer hybrid scan | ✅ |
| `anamne tag-search <prefix>` - prefix-match tag lookup | ✅ |
| `anamne shell` tab completion via stdlib readline | ✅ |

---

## What's Built (v0.24.0)

| Feature | Status |
|---|---|
| `anamne diff <id1> <id2>` - side-by-side fact comparison | ✅ |
| `anamne fact-of-the-day` - daily durable-fact reminder | ✅ |
| `anamne backup` - timestamped JSON backup to ~/.anamne/backups | ✅ |

---

## What's Built (v0.25.0)

| Feature | Status |
|---|---|
| `anamne backup --keep N` - keep only N newest backup files | ✅ |
| `anamne merge <keep_id> <drop_id>` - manual targeted fact merge | ✅ |
| `anamne merge --llm` - LLM-rewritten merged sentence | ✅ |

---

## What's Built (v0.26.0)

| Feature | Status |
|---|---|
| `anamne merge --dry-run` - preview merge without applying | ✅ |
| `anamne snapshot` - 4-section Markdown memory snapshot | ✅ |
| `anamne snapshot --output FILE` / `--limit N` | ✅ |
| Manual-merge history breadcrumb test (87 tests) | ✅ |

---

## What's Built (v0.27.0)

| Feature | Status |
|---|---|
| `anamne stash` - quick-jot working memory shorthand | ✅ |
| `anamne stash --list / --promote / --clear` | ✅ |
| `anamne snapshot --html` - HTML output variant | ✅ |

---

## What's Built (v0.28.0)

| Feature | Status |
|---|---|
| `anamne fact-of-the-day --post-to <url>` - Slack/Discord webhook payload | ✅ |
| `anamne random <N>` - sample N random facts (review/self-quiz) | ✅ |
| `anamne random --tag / --pinned` filters | ✅ |

---

## What's Built (v0.29.0)

| Feature | Status |
|---|---|
| `anamne quiz` - LLM Q&A drill against random facts | ✅ |
| `anamne template add / list / use / remove` - reusable text templates | ✅ |
| `~/.anamne/templates.json` JSON-backed template store | ✅ |

---

## What's Built (v0.30.0)

| Feature | Status |
|---|---|
| `anamne quiz --grade` - interactive prompt + LLM grade | ✅ |
| Coloured per-question verdict and final tally | ✅ |
| `anamne template export <file>` - dump JSON for sharing | ✅ |
| `anamne template import <file>` - merge in templates | ✅ |

---

## What's Built (v0.31.0)

| Feature | Status |
|---|---|
| `anamne prune --older-than YYYY-MM-DD` - bulk-prune stale facts | ✅ |
| `--tag` filter, `--keep-pinned/--no-keep-pinned`, `--yes` for prune | ✅ |
| `anamne quiz --difficulty easy\|normal\|hard` | ✅ |
| `anamne template show <name>` - print one template body | ✅ |

---

## What's Built (v0.32.0)

| Feature | Status |
|---|---|
| `anamne prune --no-retrievals-since YYYY-MM-DD` - prune unused facts | ✅ |
| Combinable with `--older-than` for "old AND unused" | ✅ |
| `anamne ask --layer episodic+scratchpad` - compound layer filter | ✅ |
| `--layer scratchpad+working` - hybrid scan without LLM | ✅ |

---

## Phase 33 - Future ideas

- **Browser extension** - "Remember this?" prompt on pages you read
- **Multi-user sharing** - export/import signed bundles with provenance
- **`anamne quiz --resume`** - continue an unfinished quiz session
- **`anamne mcp tools-list`** - introspect the running MCP tool surface
- **`anamne working --pin`** - convert a working note into a pinned scratchpad fact

---

## What This Project Is Not

Things explicitly out of scope:
- Cloud SaaS — local-first, always
- Developer SDK for app builders — that's Mem0 / Supermemory's market
- Enterprise memory governance — too much surface area for a solo project
- Replacement for AI-tool-native memory features (ChatGPT memory, Claude projects)
- Anything that requires hosting

---

## Honest Limitations

- Quality depends on what you capture. Garbage in, garbage out.
- The "brain-inspired" framing is a useful metaphor, not a neuroscience claim.
- Solo project. Bug reports may sit. Don't depend on this in production.
- Existing competitors (Mem0, Supermemory, MemPalace) are well-funded; this is the open-source,
  local-first alternative for individuals.
- `capture-clipboard` uses platform-specific fallbacks (PowerShell/pbpaste/xclip).
  For the most reliable cross-platform clipboard support, `pip install pyperclip`.

---

## Inspired By

- **LIGHT** ([arXiv 2510.27246](https://arxiv.org/abs/2510.27246)) — three-layer memory framework
- **ACT-R Memory Architecture** — temporal decay + semantic activation (Anderson & Lebiere 1998)
- **Agent Cognitive Compressor** — bounded compressed state
- **Hippocampal indexing theory** — long-term storage as compressed patterns
- **Lore protocol** ([arXiv 2603.15566](https://arxiv.org/abs/2603.15566)) — git-as-knowledge-protocol

---

## Contributing

```bash
git clone https://github.com/venumittapalli576/anamne
cd anamne
pip install -e ".[dev]"
pytest tests/
```

PRs welcome. Keep scope small. Reject feature creep.
