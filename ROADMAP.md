# PROVENANCE — Roadmap

A personal open-source project. No funding, no team, no monetization. PRs welcome.

---

## What's Built (v0.1.0)

- `Decision` data model with bi-temporal fields (created_at, valid_until)
- SQLite + ChromaDB dual store (relational + semantic search)
- Historian Agent — extracts decisions from git commits via LLM
- Oracle Agent — answers WHY questions with citations
- FastMCP server for Cursor / Claude Code integration
- Typer + Rich CLI: `init`, `index`, `ask`, `status`, `mcp-server`
- Demo script that creates a test repo with 10 realistic commits

---

## Phase 1 — Polish the Core (next)

The goal is to make the existing demo really good before adding anything new.

- **Single-command setup** — `provenance init` becomes an interactive wizard. Detects available models, picks the best free option, indexes the current repo, runs a sample query.
- **Free tier by default** — Gemini 2.5 Flash as default model (Google account, no credit card). Claude as upgrade path. Ollama as offline option.
- **Better commit filtering** — improve the regex that skips trivial commits (merges, formatting, typos). Reduce LLM API cost by 30-50% on average repos.
- **ADR auto-detection** — find ADR files in common locations (`docs/adr`, `docs/decisions`, `adr/`) without needing `--adr-dir`. Support MADR, RFC, and plain markdown.
- **Tests** — pytest coverage for the core extraction + retrieval flow.
- **Honest README + docs** — done in this commit.

---

## Phase 2 — Useful Additions (only if Phase 1 lands well)

- **VS Code extension** — thin wrapper over the CLI. Right-click a file → "Show decisions touching this file." Not a primary product, just convenience.
- **Simple web UI** — single FastAPI page showing all indexed decisions, filterable by repo / date / file. No HTMX magic, just a useful list view.
- **`provenance commit` command** — wraps `git commit`. Reads your diff, suggests a richer commit message with WHY context. User confirms or edits before commit. Solves the "garbage commits" problem at the source going forward.
- **GitHub PR descriptions ingestion** — if your team uses good PR descriptions, those are gold. Read them via `gh` CLI (no GitHub App needed).

---

## Phase 3 — Maybe / Stretch (only if Phase 2 has users)

- **Jira / Linear ticket ingestion** — read tickets the user already has access to.
- **Slack export ingestion** — parse a Slack workspace export, extract decisions from `#architecture`-type channels.
- **Staleness detection** — flag decisions that haven't been referenced in N months. Just a heuristic, not a full agent.

---

## What This Project Is Not

Things I've considered and explicitly dropped:

- **Enterprise compliance mode** — EU AI Act doesn't actually apply to this category of tool. Was hype on my part.
- **Vibe Debt Scanner** — couldn't define a real measurement. Was a buzzword.
- **6 specialist agents** (Builder, Sentinel, Mentor, Prophet) — over-engineered. The core Oracle agent already does most of what these were supposed to do.
- **Backstage plugin** — premature. Build it if someone using Backstage actually asks for it.
- **Decision Templates library** — over-engineered. Engineers can write their own templates.

---

## Honest Limitations

- Output quality depends entirely on commit message quality.
- Initial indexing of a large repo can be slow and costly.
- Ollama local mode is meaningfully worse than hosted models.
- MCP integration only works in editors that support MCP (Cursor, Claude Code, Cline, a few others).
- Solo project — bug reports may sit in the queue for a while.

---

## Contributing

Open an issue first for anything bigger than a small fix. PRs that add complexity without clear user benefit will be politely declined.

```bash
git clone https://github.com/venumittapalli576/provenance
cd provenance
pip install -e .
```
