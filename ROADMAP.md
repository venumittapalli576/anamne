# PROVENANCE — Full Roadmap

> The living memory of why your code exists.

---

## Vision

Every major AI coding tool (Cursor, Copilot, OpenClaw) reads WHAT code does.
None of them know WHY it exists. PROVENANCE fills that gap permanently.

The thesis: as AI generates more and more code, the knowledge of WHY decisions
were made becomes MORE valuable, not less. Codebases will grow faster than ever,
but the institutional memory of why things exist will disappear even faster —
unless something captures it.

PROVENANCE is that thing.

---

## Phase 0 — Core Infrastructure (COMPLETE)

**Goal:** Working CLI that indexes a git repo and answers WHY questions.

### What was built

- `provenance/models.py`
  - `Decision` dataclass with bi-temporal fields (created_at + valid_until)
  - `is_stale()` method to detect outdated decisions
  - `to_dict()` for JSON serialization

- `provenance/config.py`
  - Pydantic-settings based config
  - Reads ANTHROPIC_API_KEY, MODEL, DATA_DIR from .env

- `provenance/store/graph.py` — Dual storage engine
  - SQLite: temporal/relational store (full history, timestamps, repos)
  - ChromaDB: semantic vector store (similarity search)
  - `add()`, `add_many()`, `search()`, `get_by_repo()`, `count()`, `all_repos()`

- `provenance/agents/historian.py` — Historian Agent
  - Reads git log via GitPython
  - Filters trivial commits (merges, typos, fmt, lint, wip)
  - Calls Claude to extract structured decisions from commit messages
  - Returns list of Decision objects
  - Also indexes ADR markdown files

- `provenance/agents/oracle.py` — Oracle Agent
  - Semantic search for relevant decisions
  - Calls Claude with decision context to answer WHY questions
  - Rich-formatted output with citations and staleness warnings

- `provenance/mcp/server.py` — FastMCP Server
  - `ask_why(question)` — answer WHY questions
  - `search_decisions(query, limit)` — raw decision search
  - `get_file_context(file_path)` — file-specific decisions
  - `get_stats()` — knowledge base stats
  - stdio transport for Cursor/Claude Code

- `provenance/cli/main.py` — Typer CLI
  - `provenance init` — set up .env and data dir
  - `provenance index <repo>` — index a repo
  - `provenance ask "<question>"` — ask a WHY question
  - `provenance status` — show knowledge base stats
  - `provenance mcp-server` — start MCP server

- `scripts/create_test_repo.py` — Demo repo generator
  - Creates a fake ShopAPI git repo with 10 realistic commits
  - Includes: Redis caching, JWT->opaque tokens, Stripe choice, Elasticsearch, Celery

### Tech Stack Decisions

- **Python 3.12** — no Node.js needed
- **FastMCP** — Python MCP framework, 70% less boilerplate than official SDK
- **ChromaDB** — embedded vector store, zero config, Rust-rewritten (4x faster)
- **SQLite** — embedded relational store, temporal queries, zero config
- **Typer + Rich** — beautiful CLI with zero boilerplate
- **Pydantic-settings** — clean config with .env support
- **GitPython** — pure Python git access
- **Anthropic SDK** — Claude for extraction and answering
- **MIT License** — most viral open-source license, H1B safe

---

## Phase 1 — Integrations

**Goal:** Ingest knowledge from more than just git.

### 1.1 ADR File Indexing (Scaffolded in Phase 0)
- `provenance index --adr-dir ./docs/decisions` already works
- Improve: auto-detect ADR directories (docs/decisions, docs/adr, adr/)
- Support: MADR format, RFC format, plain markdown

### 1.2 GitHub PR Context
- Index PR descriptions and review comments as decisions
- Use GitHub API (no scraping, user provides token)
- Link decisions to specific files changed in the PR

### 1.3 Jira / Linear Ticket Ingestion
- Read tickets via API using user's own credentials
- Extract architectural decisions from ticket descriptions
- Link decisions to commits that reference the ticket number

### 1.4 Slack Export Ingestion
- User exports their own Slack workspace (Settings -> Export)
- Parse the export ZIP — no API needed, no ToS issues
- Extract decisions from #architecture, #tech-decisions channels
- Slash command bot: /provenance capture "we chose Postgres because..."

### 1.5 Watch Mode
- `provenance watch .` — background process
- Auto-index new commits as they land
- Notify when a new decision is captured

---

## Phase 2 — More Agents

**Goal:** Go beyond answering questions — actively help the team.

### 2.1 Sentinel Agent — PR Review
- Hooks into GitHub Actions / pre-push hook
- Compares staged changes against existing decisions
- Warns: "This change contradicts the Redis caching decision from 2023"
- Posts review comment with context and source

### 2.2 Mentor Agent — Developer Onboarding
- `provenance mentor <file_path>`
- Generates a WHY-annotated tour of a file
- "This auth middleware exists because of SEC-1234 (XSS audit, 2024)"
- Great for onboarding new team members

### 2.3 Builder Agent — WHY-Aware Code Generation
- `provenance build "add rate limiting to /products"`
- Checks existing decisions before generating code
- "Found decision: Redis is the caching layer (2024-03-15). Using Redis for rate limiting."
- Generates code consistent with past decisions

### 2.4 Prophet Agent — Staleness Detection
- Scans all decisions and checks if they're still valid
- "The Elasticsearch decision is 18 months old — has the search strategy changed?"
- Flags decisions marked with valid_until dates that have passed
- Weekly digest: "These 3 decisions may be outdated"

---

## Phase 3 — Enterprise Features

**Goal:** Make PROVENANCE the compliance and audit layer for AI-generated code.

### 3.1 Vibe Debt Scanner
- Tracks what percentage of code was AI-generated
- Scores codebase by: AI code %, WHY coverage, decision freshness
- Dashboard: "42% of your code is AI-generated with no WHY context"
- Alert: "Vibe debt increasing — 15 new files this week with no decision context"
- This is a 2026 problem that no one else is solving

### 3.2 EU AI Act Compliance Mode
- Mandatory from August 2, 2026 for "high-risk" AI systems
- Article 11: Auto-generates technical documentation from decision history
- Article 12: Audit log of all AI-assisted decisions with timestamps
- `provenance compliance-report` — outputs PDF/HTML audit document
- This is a real market gap — zero existing tools handle this

### 3.3 Web Dashboard
- FastAPI backend + HTMX frontend (no JavaScript framework needed)
- Visual timeline of decisions
- Dependency graph: which decisions depend on which
- Search and filter UI
- Docker Compose: `docker compose up`

### 3.4 Docker Compose Deployment
```yaml
services:
  provenance:
    image: ghcr.io/venumittapalli576/provenance
    ports: ["8080:8080"]
    volumes: ["~/.provenance:/data"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

### 3.5 Model-Agnostic Support
- Current: Claude (default)
- Add: Gemini 2.5 Flash (free tier, Apache 2.0)
- Add: Ollama (fully offline, zero API costs)
- Add: Any OpenAI-compatible API
- Config: `MODEL=ollama/llama3.2` or `MODEL=gemini/gemini-2.5-flash`

---

## Why This Will Succeed

### Problems it solves that NO ONE else solves

1. **Knowledge debt is exploding** — AI coding tools generate code 10x faster
   but generate ZERO documentation of why. This problem gets worse every day.

2. **Team onboarding costs $50k+ per engineer** — most of it is figuring out
   why things work the way they do. PROVENANCE cuts that.

3. **EU AI Act** — mandatory compliance by Aug 2026. No tool exists for this.
   PROVENANCE is the only tool positioned to solve it.

4. **Vibe coding creates vibe debt** — the 2026 technical crisis that's already
   starting. First mover advantage here is massive.

### Why open source wins

- Cursor is $20/month and proprietary
- Copilot is $10/month and Microsoft-controlled
- PROVENANCE is free, self-hosted, and MIT licensed
- Enterprise teams WANT self-hosted for security/compliance
- Open source builds trust and adoption faster than any marketing

### Competitive moat

- First mover in the WHY layer
- MCP compatibility means it works WITH Cursor/Copilot, not against them
- Self-hosted = enterprise buyers who can't use cloud tools
- EU compliance = captive European market with no alternatives

---

## Legal / Compliance Notes

- MIT License — most permissive, H1B safe as non-commercial hobby project
- No Slack API usage — uses user's own export files (no ToS issues)
- No GitHub API scraping — uses official API with user's own token
- BYOK (Bring Your Own Key) — no data sent to Anthropic except user's own prompts
- Zero telemetry — no analytics, no tracking, no phone-home
- EU AI Act ready by design — audit logs built into the data model

---

## Contributing

Areas where help is needed:

- [ ] ADR format auto-detection (MADR, RFC, plain markdown)
- [ ] GitHub PR integration
- [ ] Jira/Linear connectors
- [ ] Sentinel Agent (PR review hooks)
- [ ] Prophet Agent (staleness detection)
- [ ] Web Dashboard (FastAPI + HTMX)
- [ ] Docker Compose setup
- [ ] Gemini / Ollama model support
- [ ] EU compliance report generator
- [ ] VS Code extension

---

## Timeline Estimate

| Phase | Scope | Estimated Time |
|---|---|---|
| Phase 0 | Core (CLI, agents, MCP) | Complete |
| Phase 1 | Integrations (GitHub, Jira, Slack) | 3-4 weeks |
| Phase 2 | More agents (Sentinel, Mentor, Builder, Prophet) | 4-6 weeks |
| Phase 3 | Enterprise (Vibe Debt, EU Act, Dashboard) | 6-8 weeks |

Total to full v1.0: ~3 months with focused effort.
