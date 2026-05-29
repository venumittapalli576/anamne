# Changelog

All notable changes to ANAMNE are documented here.

---

## [1.2.0] — 2026-05-28

Reproducible retrieval benchmark. A memory layer's whole job is finding the
right memory — this release lets anyone prove ANAMNE does, fully local, no
API key, in under a minute.

### Added

- **`anamne bench`** — runs the bundled retrieval benchmark and prints a
  rich comparison table (recall@k, hit@1, MRR, p50/p95 latency) across three
  strategies: `substring`, `semantic`, and `hybrid` (the production default).
  Flags: `-k`, `--strategy` (repeatable), `--by-type`, `--json`.
- **Bundled benchmark dataset** (`anamne/bench/dataset.json`) — 48
  personal-style facts and 32 labelled natural-language queries (keyword /
  paraphrase / multi / distractor) with per-query relevance labels.
- **`benchmark_recall` MCP tool** (22 tools total) — lets an AI client run
  the benchmark and get structured results plus a one-line headline.
- **`DecisionStore.close()`** — releases the ChromaDB client through its own
  refcounted `Client.close()`, so a throwaway store tears its data directory
  down cleanly (notably on Windows, where the open SQLite handle blocked
  deletion). Refcount-aware: a coexisting store on another path is untouched.

### Results

On the bundled dataset (48 facts / 32 queries, k=5, local MiniLM embedder):

| Strategy | recall@5 | hit@1 | MRR |
|---|---|---|---|
| substring | 0% | 0% | 0.00 |
| semantic | 97% | 91% | 0.94 |
| **hybrid** | **97%** | **91%** | **0.94** |

The literal-substring baseline scores 0% because the queries are real
questions, not keyword echoes — which is exactly why embeddings matter.

### Verified

- 14 new benchmark tests (dataset integrity + harness behaviour). The
  harness always builds an isolated throwaway store and never reads or writes
  the user's real `~/.anamne` data.
- Confirmed zero temp-directory leaks, and that a coexisting real store keeps
  working after the benchmark closes its own client (the in-process
  `benchmark_recall` path).
- Full test suite passing.

---

## [1.1.0] — 2026-05-13

Dashboard redesign: warm paper aesthetic, light-by-default, new Home tab,
theme toggle. The previous Linear-style dark-only dev-tool look fought the
"personal memory layer" concept; this release leans into notebook
typography and quiet earth-tone accents.

### Changed

- **Light theme is now the default.** Warm cream paper (`#FAF7F1`) on
  deep ink (`#1F1D1A`), with subtle radial backdrop gradients for paper
  feel. The previous slate-on-black dark theme remains available via the
  new toggle.
- **Serif headlines via Fraunces** (Google Fonts), Inter for body,
  JetBrains Mono for IDs/numbers.  Numbers in stat cards use Fraunces too
  for a notebook-style "table of contents" feel.
- **Earth-tone layer accents** replace v1.0.5's jewel tones:
  - Scratchpad → deep indigo `#4F46E5`
  - Working   → forest moss  `#2D6A4F`
  - Episodic  → sienna       `#92400E`
- **Stripped chrome.** No card backgrounds on tables, no
  hover-glow on stat cards, no card padding around content blocks.
  Content flows on the paper.

### Added

- **`Home` tab** is the new default landing.  Shows a one-sentence summary
  of memory state, the 5 most recent facts, active working memory, and a
  "Getting started" snippet when the store is empty (replaces the
  previous "land on an empty fact table" UX).
- **Theme toggle** (top-right `☾` / `☀`) flips between light and dark.
  Choice persists across reloads via `localStorage`.

### Implementation notes

- Backwards compatible: every existing class name and ID is preserved, so
  the JS that handles tab switching, fact rendering, and graph layout
  required no changes other than adding `loadHome()` + `toggleTheme()`.
- Dark theme is a CSS-variable override via `body[data-theme="dark"]`;
  the same per-layer `--accent` rewiring still works in both themes.

### Verified

- Live-rendered the dashboard in a headless browser; confirmed:
  - Background renders as `rgb(250, 247, 241)` (cream)
  - H1 font resolves to `Fraunces` (serif loaded)
  - `Home` is the active tab on load, with the new layout
  - Tab clicks correctly shift `--accent` (scratchpad → indigo,
    working → moss, episodic → sienna) and the sidebar's active marker
    color matches
  - Theme toggle flips background to `rgb(15, 14, 12)` and writes
    `"dark"` to `localStorage`; toggle back restores `"light"`
  - Zero JS console errors
- 103 unit + integration tests still passing.

---

## [1.0.9] — 2026-05-13

Closes both remaining open issues (#3 and #4).

### Fixed - issue #4: remember/search race

`DecisionStore.remember()` does (a) SQLite INSERT then (b) ChromaDB upsert.
Before this fix, an MCP client (or any code) that dispatched
`remember()` and `search_facts_semantic()` to different threads in parallel
could observe a state where the SQLite row existed but the ChromaDB
embedding wasn't yet committed - causing the semantic search to miss the
just-stored fact.

- Added `threading.RLock` to `DecisionStore`.
- `remember()` holds the lock across BOTH writes (SQLite + ChromaDB upsert).
- `search_facts()` and `search_facts_semantic()` acquire the lock at the
  start of the read path, so they wait for any in-flight write to finish.
- RLock (re-entrant) avoids self-deadlock when methods call each other
  (e.g. `search_facts_ranked` -> `search_facts` + `search_facts_semantic`).

Regression test: `test_remember_search_no_race_under_concurrent_threads`
spawns concurrent writer + reader threads on 30 facts. Without the lock,
some facts intermittently appeared missing under semantic search; with the
lock, all 30 are reliably found.

### Added - issue #3: iter_facts() generator for large stores

Added `DecisionStore.iter_facts(batch=1000, tags=None)` which streams
facts in pages instead of materialising the full set in Python memory.
Memory bound is O(batch) instead of O(N) - allows commands to run
constant-memory on stores of any size.

Refactored two commands the issue specifically called out:
- `anamne tags` - tag counter now streams; memory bound is O(unique tags),
  not O(all facts).
- `anamne snapshot` - rebuilt as a single streaming pass that uses
  `heapq.nsmallest`-style top-K filtering for the "Top activation" section
  and bounded accumulation for "Recent (7 days)". Previously materialised
  every fact, sorted in Python; now uses the generator.

Regression test: `test_iter_facts_streams_in_pages` seeds 250 rows directly
via SQLite (bypassing ChromaDB to keep the test fast), verifies the
generator yields them in 50-row batches with the correct dict shape, and
that tag filtering works in streaming mode.

Other commands listed in the issue (`backup`, `export`, `stats`,
`tag-stats`, `profile`, `suggest-pins`, `sync-cloud`, `audit-log`) still
use `list_facts()` because they genuinely need the full set materialised
(JSON dump, sort across all facts, etc.). They remain on the existing API
and would benefit from a future profiling pass if a user actually hits
50k+ facts.

### Tests

- 103 tests, all passing (+2 new regression tests).

---

## [1.0.8] — 2026-05-13

### Fixed

- **SSRF guard now runs BEFORE the API-key check.** v1.0.6 placed the URL
  validation after `_require_api_key()`, which meant any caller (or any CI
  environment) without an LLM key would exit early on the API-key error
  before the SSRF guard ever fired. The 8 SSRF regression tests passed
  locally (where API keys are configured) but failed on Ubuntu / macOS /
  Windows CI runners (which have no keys). More importantly, this meant
  the security guard was actually unreachable for any LLM-less use of the
  command.

  The fix: `_is_safe_url()` and its check run first, before any LLM-touching
  code. URL validation is pure stdlib (`urllib.parse`, `ipaddress`, `socket`)
  and doesn't need an API key. `_require_api_key()` runs only after the
  SSRF check passes, since the key is only needed for the distillation step
  later.

  Implementation discipline: **security checks should never depend on
  having credentials**, otherwise a stripped-down attacker context bypasses
  them.

### Tests

- 101 tests, all passing. Same 11 security regression tests as v1.0.7,
  but now they actually pass on CI too (reproduced locally with
  `env -i PATH=... HOME=... anamne import-web ...` and verified the
  "Refusing to fetch" message fires correctly).

---

## [1.0.7] — 2026-05-13

### Fixed

- **UI server concurrency bug.** `anamne ui` used `http.server.HTTPServer`,
  which is single-threaded. Browsers routinely make 4-6 parallel requests
  when loading a page (`/`, `/api/stats`, `/api/facts`, etc.), and any
  one stuck connection (slow ChromaDB query, abandoned curl, MCP probe
  holding the socket) would block every subsequent request. Replaced
  with `ThreadingHTTPServer`. Verified by a parallel-request stress test:
  5 concurrent `/api/stats` requests now complete in ~2.2s each instead
  of serialising.

  This was discovered during the manual UI verification of the v1.0.6
  security audit — it isn't a vulnerability per se, but it's a real DoS
  in practice (any stuck request hangs the whole dashboard).

### Added

- `test_ui_uses_threading_http_server` regression test pinning the fix so
  a future refactor cannot silently re-introduce the single-threaded
  server.

### Tests

- 101 tests, all passing (+1 new threading regression).

---

## [1.0.6] — 2026-05-12

**Security audit + bug fix release.** Ran the full Python security stack
(bandit, pip-audit, ruff) plus a manual review of every attack surface
(UI server, MCP server, web import, subprocess calls). All real findings
fixed below; false positives documented.

### Fixed - security

- **SSRF in `anamne import-web`** (high). Previously the command would fetch
  any URL the caller provided, including `http://localhost:*`, AWS metadata
  (`http://169.254.169.254`), private RFC1918 ranges, and non-http schemes
  like `file://`. An attacker controlling a connected MCP client (or just a
  malicious crawl link) could pivot into the user's local network or read
  cloud-instance secrets. Now `_is_safe_url()` rejects:
  - Non-http(s) schemes (file, ftp, gopher, etc.)
  - Hostnames in a blocklist (`metadata.google.internal`, ...)
  - Any address that resolves to a loopback, private, link-local, multicast,
    reserved, or unspecified IP.
  - Re-checked on every URL during `--crawl`, not just the initial one.

- **XSS in dashboard fact graph tooltip** (medium). The tag-node tooltip and
  the tag list on fact-node tooltips rendered tag names without HTML
  escaping. A tag containing markup (e.g. via an untrusted `tag_fact` MCP
  call) would execute when the user hovered the node. Both sites now go
  through `escHtml()`.

- **Dependency vulnerability**: `gitpython>=3.1.40` floor bumped to
  `>=3.1.50` to pull in the fix for `GHSA-mv93-w799-cj2w`.

### Fixed - bugs

- **`netloc.lstrip("www.")` was wrong** in `import-web`. `lstrip` takes a set
  of characters, so `"awesome.com".lstrip("www.")` returns `"esome.com"`,
  not `"awesome.com"`. Replaced with `removeprefix("www.")` which does the
  prefix-aware thing.

### Tests

- New `tests/test_security.py` with 10 regression tests:
  - 8 parametrised cases covering SSRF blocking (localhost, AWS metadata,
    GCP metadata, RFC1918 ranges, file://, ftp://)
  - 1 case asserting both XSS escape sites in the graph tooltip
  - 1 case pinning the `removeprefix("www.")` fix in source
- 100 tests, all passing (was 90).

### Code quality

- `ruff` auto-fix removed 18 unused imports and redundant f-strings across
  the codebase.
- Remaining lint findings audited:
  - 6 bandit "SQL injection" warnings are confirmed false positives —
    they flag `f"... WHERE id IN ({placeholders})"` where `placeholders`
    is literally `"?" * len(ids)` joined with commas (no user input).
  - 6 remaining ruff F841 (unused variable) hits are intentional test
    fixtures.

---

## [1.0.5] — 2026-05-12

### Changed
- **Three-layer color identity in the dashboard.** Each of the three memory
  layers (scratchpad / working / episodic) now has its own accent color,
  reflecting the actual cognitive model of the product:
  - **Scratchpad → violet** (`#a78bfa`) — calm, durable, "memory itself"
  - **Working → mint** (`#34d399`) — fresh, transient, active
  - **Episodic → amber** (`#fbbf24`) — warm, archival, remembered
- Header stat cards are permanently tinted by their layer (always visible at
  a glance). The active-tab accent shifts dynamically when you switch tabs —
  the entire dashboard recolors to match the layer you're inspecting.
- **Per-tag color hashing.** Each tag gets a unique HSL hue derived from a
  stable hash of its name, so `python`, `architecture`, `journal` are all
  visually distinct across the whole UI without any manual config.
- Pure CSS + minimal JS (one `body.dataset.layer` assignment in `showTab`,
  one `tagHue()` helper). No backend changes.

### Why
v1.0.4 was a Linear-class visual refresh but treated all three memory layers
identically. The single most defensible design move for a product literally
named after memory is to give each layer its own visual identity. This is
distinctive, grounded in the product's actual architecture, and adds real
information density (you can tell at a glance which layer a fact lives in).

### Tests
- 90 tests, all passing (no functional changes).

---

## [1.0.4] — 2026-05-12

### Changed
- **`anamne ui` dashboard visual refresh.** Single-pass redesign of the web
  dashboard — no new tabs, no new features, no backend changes; pure visual
  layer overhaul:
  - New palette: deeper slate background with violet accent (was GitHub gray
    with blue accent); ambient radial gradients for depth
  - Typography: Inter for body, JetBrains Mono for IDs / monospace; tighter
    letter spacing, confident size hierarchy
  - Header: stat cards with hover lift, glowing logomark, sticky positioning
  - Sidebar: rounded buttons with active-state accent bar; better hit areas
  - Tables wrapped in soft cards with hairline borders and row hover
  - Buttons / inputs: focus rings with accent glow
  - Spinners now animate; modal has backdrop blur
  - Fact Graph background gains subtle radial gradient
  - Custom thin scrollbar styling
- No JS, markup structure, or backend code changed. All class names and IDs
  preserved so behavior is byte-identical to v1.0.3.

### Tests
- 90 tests, all passing (no changes).

---

## [1.0.3] — 2026-05-12

Documentation-only patch release. No code changes.

### What this picks up on PyPI

The previous PyPI release (v1.0.2) shipped with a README that was missing
the personal-project disclaimer and contained an incorrect citation. The
fixes were committed but PyPI snapshots the README at publish time, so
they hadn't propagated to the PyPI project page.

This release re-publishes so the PyPI page matches the GitHub README.

### Changed
- README now leads with a prominent "Personal open-source project, not
  commercial" disclaimer.
- Agent Cognitive Compressor citation corrected from `arXiv 2510.27246`
  (LIGHT's ID) to `arXiv 2601.11653` (ACC's actual ID).
- Added a four-question MCP troubleshooting section to the README.
- Removed `BLOG_POST.md` (preserved outside the repo).
- Updated `.env.example` to use ANAMNE branding and accurate variable
  names; documented signing/encryption keys.

### Tests
- 90 tests, all passing (no changes).

---

## [1.0.2] — 2026-05-12

### Fixed
- **MCP server boots without an LLM API key.** Previously, `anamne mcp-server`
  would refuse to start if neither `ANTHROPIC_API_KEY` nor `GEMINI_API_KEY`
  was set. Since Claude Code / Cursor spawn the server as a subprocess that
  doesn't always inherit the user's shell environment, this caused silent
  failures — the MCP tool surface would appear empty and there'd be no
  indication why.
- The fix: lazy-construct `OracleAgent` only when an LLM-dependent tool
  (`ask_why`, `consolidate_facts`) is actually called. The other 19 tools
  (memory reads, writes, working memory, pin/unpin, related, etc.) work
  with no LLM at all.
- Boot-time stderr message updated to reflect partial-mode behaviour.

### Added
- **Cross-platform CI matrix.** GitHub Actions now runs the full test suite
  on `ubuntu-latest`, `windows-latest`, and `macos-latest`. Closes #1.
- New integration test `test_mcp_server_imports_without_api_key` covers the
  no-key boot path so this regression cannot return silently.

### Tests
- 90 tests, all passing (+1 covering the no-key MCP boot path)

---

## [1.0.1] — 2026-05-12

First patch release. Fixes discovered during real stdio-handshake testing
of the v1.0.0 release.

### Fixed
- MCP server now reports its own version (e.g. `anamne 1.0.1`) instead of
  FastMCP's framework version (`anamne 3.2.4`). Clients can now reliably
  detect anamne upgrades from the `initialize` response.

### Added
- `tests/test_mcp_integration.py`: full end-to-end stdio handshake test
  that boots `anamne mcp-server` as a subprocess, performs the MCP
  `initialize` + `tools/list` flow, and asserts every registered tool
  surfaces over the wire. Closes #2.
- Skipped automatically in CI when no LLM API key is configured.

### Why this matters
While validating the v1.0.0 release, the integration test caught a real
loose end: the MCP server was reporting `anamne 3.2.4` (the FastMCP
framework version) instead of the package version. Without this fix,
client-side version detection of anamne would have been impossible.

### Tests
- 89 tests, all passing (+2 new MCP integration tests)

---

## [1.0.0] — 2026-05-12

First stable release.

### Audit & stabilization

After 32 phases of feature work in the v0.x series, the command surface
was audited and the canonical v1.0 surface was published in `STABLE.md`.

- **39 commands kept visible** as the stable v1.x surface
- **33 commands marked `hidden=True`** — still functional but off the menu;
  reserved for power users and not covered by the stability promise
- `STABLE.md` documents the stable command set and the v1.x stability
  promise (no breaking changes to visible commands within v1.x)
- Project classifier moved from Beta to Production/Stable

### Hidden in v1.0 (still callable by name)

Search variants: `recall`, `similar`, `related`, `search-all`
Tag variants: `bulk-tag`, `tag-clear`, `tag-stats`, `tag-search`
Display variants: `recent`, `quote`, `mark`, `random`, `fact-of-the-day`,
`snapshot`, `profile`, `recap`, `timeline`, `tail`, `reminder`, `stash`
LLM novelties: `quiz`, `template`, `suggest-pins`, `suggest-tags`
Fact ops: `diff`, `merge`, `promote`
Advanced: `notebook`, `sync-cloud`, `key-rotate`, `audit-log`, `watch-repos`,
`tool-call`

### Tests
- 87 tests, all passing

---

## [0.45.0] — 2026-05-12

### Added - Phase 45

**`anamne shell` history persistence**
- Up-arrow recall works across REPL sessions
- Stored at `~/.anamne/shell-history`, capped at 2000 entries
- Written on exit via `atexit`; silently skipped where `readline` is unavailable

**`anamne tools --grep <substr>`**
- Filter the MCP tool list by case-insensitive substring match against
  name OR first-line description
- Composes with `--json`

**`anamne snapshot --include-archived`**
- Appends a section listing fact-history events from the last 7 days
- Shows `content_updated`, `forgotten`, and `merged_into` rows with snippets
- Useful for catching "what got deleted/merged this week"

### Tests
- 87 tests, all passing

---

## [0.44.0] — 2026-05-12

### Added - Phase 44

**`anamne tool-call --help-tool`** - print tool signature + docstring
- No execution; just shows what the tool expects and what it does
- Great companion to `anamne tools` for exploring the surface

**`anamne audit-log --tail --json`** - structured tail stream
- Emits one JSON object per new event (`{fact_id, change_type, hash, ...}`)
- Pipe-friendly: `anamne audit-log --tail --json | jq`

**`anamne sync-cloud --schedule --once-then-exit`** - cron-mode
- Runs exactly one sync and exits (no infinite loop)
- Pairs naturally with system cron / Task Scheduler

### Tests
- 87 tests, all passing

---

## [0.43.0] — 2026-05-12

### Added - Phase 43

**`anamne tool-call <name> <json-args>`** - direct MCP tool invocation
- Calls any MCP tool exactly as Claude / Cursor would, from the CLI
- No LLM, no MCP client needed - useful for scripts and quick checks
- Returns pretty-printed JSON for dict/list results
- Reports the tool's signature on bad arguments

**`anamne audit-log --tail`** - live hash-chain tail
- Bootstraps the rolling hash by replaying existing rows, then polls every
  5s and prints any new fact_history row plus its updated chain hash
- Ctrl-C stops cleanly

**`anamne sync-cloud --schedule N`** - foreground sync daemon
- Re-runs the push every N seconds (Ctrl-C to stop)
- Push-only; `--pull` + `--schedule` is rejected as ambiguous
- Survives transient errors (logged inline, loop continues)

### Tests
- 87 tests, all passing

---

## [0.42.0] — 2026-05-12

### Added - Phase 42

**`anamne audit-log --since / --until`** - windowed audit chain
- Recompute the hash chain over a date window only
- Useful for cron jobs that anchor a daily window's head hash

**`anamne audit-log --json`** - structured stdout
- Emits `{length, head, entries: [...]}` for piping into jq / dashboards

**`anamne sync-cloud --encrypt`** - encrypted git mirror push
- Wraps `anamne-export.json` in the AES-GCM envelope before committing
- Uses the same `ANAMNE_ENC_KEY` env var as `export --encrypt`

**`anamne sync-cloud --pull --decrypt`** - transparent encrypted-mirror ingest
- Auto-detects envelope format; `--decrypt` forces the path explicitly
- Works end-to-end: push --encrypt on machine A, pull on machine B reads
  the same AES-GCM envelope

### Tests
- 87 tests, all passing

---

## [0.41.0] — 2026-05-11

### Added - Phase 41

**`anamne audit-log --verify <head>`** - exit-coded chain check
- Exits 1 unless the current chain head exactly matches the supplied hash
- Uses `hmac.compare_digest` for constant-time comparison
- Designed for cron-style scripts: record the head once, then verify daily

**`anamne audit-log --remote-anchor <url>`** - publish head to a webhook
- POSTs `{anamne_audit, length, head, text}` to the URL
- Slack/Discord-compatible (`text` is a pre-formatted summary)
- Pair with `--verify` later to detect drift between machines

### Tests
- 87 tests, all passing

---

## [0.40.0] — 2026-05-11

### Added - Phase 40

**`anamne audit-log`** - tamper-evident audit log
- Walks `fact_history` in chronological order
- Computes a rolling SHA-256 hash chain (each row's hash includes the previous
  hash + the event content)
- `--check` prints just the chain length + head hash for periodic comparison
- `--output <file>` writes the full JSONL chain (each line = one entry)
- `--limit N` caps the displayed view (most recent first)

**Composable `export --encrypt --signed`** - already worked, now documented
- Sign is computed before encryption, so the envelope-decrypt path naturally
  yields a payload whose `_signature` is verifiable

### Tests
- 87 tests, all passing

---

## [0.39.0] — 2026-05-11

### Added - Phase 39

**`anamne export --encrypt`** - AES-GCM envelope export
- Wraps the export JSON in a tiny `{_anamne_envelope, nonce, ciphertext}`
- Key derived from `ANAMNE_ENC_KEY` via SHA-256 (32-byte AES-256 key)
- Random 12-byte nonce per export; payload is JSON-serialized first
- Requires `pip install cryptography` (lazy-imported, friendly error if missing)

**`anamne import-memory --decrypt`** - decrypt envelopes on import
- Auto-detected when the file has `_anamne_envelope`; `--decrypt` makes it
  explicit
- Re-derives the AES key from `ANAMNE_ENC_KEY`
- Verifies + decrypts, then proceeds with the normal import flow (composable
  with `--verify`)

**`anamne key-rotate <dir>`** - re-sign bundles with a new HMAC key
- Reads every JSON file matching `--glob` (default `*.json`)
- Verifies the existing `_signature` against `ANAMNE_SIGN_KEY_OLD`
- Re-signs with `ANAMNE_SIGN_KEY` and writes back in place
- `--dry-run` to preview which files would rotate
- Reports rotated / bad-old-sig / unsigned counts

### Tests
- 87 tests, all passing

---

## [0.38.0] — 2026-05-11

### Added - Phase 38

**`anamne export --signed`** - HMAC-signed export bundles
- Appends a `_signature` block (`{algo: HMAC-SHA256, value: ...}`)
- Signing key read from the `ANAMNE_SIGN_KEY` environment variable
- Signature is computed over the canonical JSON sorted-keys representation
  of the payload WITHOUT the signature itself

**`anamne import-memory --verify`** - signature verification on import
- Recomputes the HMAC using `ANAMNE_SIGN_KEY` and refuses to import on
  mismatch (or when no signature is present)
- Uses `hmac.compare_digest` for constant-time comparison
- Pairs naturally with team-shared bundles where you want to confirm the
  file came from a known sender

### Tests
- 87 tests, all passing

---

## [0.37.0] — 2026-05-11

### Added - Phase 37

**`anamne sync-cloud --pull`** - one-way ingest from git mirror
- Reads `anamne-export.json` from the local git repo and additively merges
  the scratchpad facts into local memory
- Skips facts whose `id` already exists locally (idempotent)
- `--yes` skips the confirmation prompt
- You still run `git pull` yourself first; the command only does the import

**`anamne notebook --runnable`** - notebook with live-query code cell
- Adds a code cell at the top using the ANAMNE Python API to re-fetch facts
- Reader's machine needs ANAMNE installed; static markdown cells still work
  without it

### Tests
- 87 tests, all passing

---

## [0.36.0] — 2026-05-11

### Added - Phase 36

**`anamne mcp-config --apply`** - write the snippet directly to the client
- Auto-detects `~/.claude.json` (Linux/macOS) or `%APPDATA%\Claude\...` (Windows)
- Merges into `mcpServers`, preserves any other entries
- `--config-path` to override the location
- Cursor still prints-only (Cursor uses an in-app dialog, not a JSON file)

**`anamne sync-cloud --repo <git-repo>`** - personal git-backed mirror
- Writes `anamne-export.json` to the given local git repo
- Stages, commits (`anamne sync ...` message default), and pushes
- `--no-push` for offline-only commits
- Idempotent: skips the commit when there are no changes

### Tests
- 87 tests, all passing

---

## [0.35.0] — 2026-05-11

### Added - Phase 35

**`anamne mcp-config`** - pre-filled MCP config snippets
- `--client claude` (default), `cursor`, or `cline`
- Auto-detects the absolute path to the local `anamne` executable
- Prints a paste-ready JSON block plus the target file path

**`anamne notebook <file.ipynb>`** - Jupyter notebook export
- One markdown cell per fact, with id + tags + pinned indicator
- `--tag X` filters; `--limit N` caps facts (default 200)
- Recipient needs Jupyter only, not ANAMNE

**`anamne diff --history`** - compare current vs previous fact version
- Diffs against the most recent meaningful entry in `fact_history`
- Useful right after `anamne edit` to verify what changed
- Falls back gracefully when no history exists

### Tests
- 87 tests, all passing

---

## [0.34.0] — 2026-05-11

### Added - Phase 34

**`anamne tools --schema <name>`** - dump full JSON schema for one tool
- Prints the tool's name, description, and `inputSchema` parameters
- Helps verify exactly what an AI client will see when calling the tool

**`anamne working --to-fact <id>`** - promote without pinning
- Symmetric counterpart to `--pin`: moves a working note to scratchpad
  without protecting it from auto-consolidation
- `--tag` attaches tags during promotion

**`anamne quiz --resume`** - continue an unfinished quiz session
- Saves pending question ids to `~/.anamne/quiz-state.json` after each item
- Ctrl-C mid-grade keeps the in-flight question as the next "pending" item
- `--resume` re-hydrates the remaining facts and continues
- State file is cleared automatically when a quiz completes

### Tests
- 87 tests, all passing

---

## [0.33.0] — 2026-05-11

### Added - Phase 33

**`anamne working --pin <working_id>`** - promote and pin in one step
- `anamne working --pin abc123 --tag db` moves a working note to scratchpad
  and pins it atomically
- Two-call shortcut for the most common "this turned out to be permanent"
  workflow

**`anamne tools`** - list every MCP tool the server exposes
- Prints each tool name + first-line description
- `--json` for machine-readable output
- Lets you verify Claude/Cursor will see the expected capabilities before
  wiring up `mcp-server`

### Tests
- 87 tests, all passing

---

## [0.32.0] — 2026-05-11

### Added - Phase 32

**`anamne prune --no-retrievals-since YYYY-MM-DD`** - prune unused facts
- Deletes facts that have NOT been retrieved since the cutoff
- Combinable with `--older-than` (both conditions must hold)
- Same `--tag` / `--keep-pinned` / `--yes` flags as the date-only variant

**`anamne ask --layer episodic+scratchpad`** - compound layer filter
- `--layer` now accepts `+`-joined layer combinations
- `scratchpad+working` runs both layers without needing an LLM
- Episodic-included combinations still route through the Oracle
- Unknown layer names rejected with a clear error

### Tests
- 87 tests, all passing

---

## [0.31.0] — 2026-05-11

### Added - Phase 31

**`anamne prune --older-than YYYY-MM-DD`** - bulk-prune stale facts
- Deletes scratchpad facts created before the ISO cutoff
- `--tag X` restricts the scope
- `--keep-pinned` (default true) preserves pinned facts; flip with
  `--no-keep-pinned`
- Always prints a preview (first 10) before deleting; `--yes` skips confirm

**`anamne quiz --difficulty easy | normal | hard`** - difficulty knob
- `easy`: direct recall, surface wording close to the fact
- `hard`: synthesis / application; surface wording deliberately distant
- Difficulty drives the question-generation prompt only - grading still
  compares against the LLM's reference answer

**`anamne template show <name>`** - print one template body
- Useful before `template use` when you've forgotten the placeholder names

### Tests
- 87 tests, all passing

---

## [0.30.0] — 2026-05-11

### Added - Phase 30

**`anamne quiz --grade`** - interactive grading mode
- Asks the user for an answer at the terminal
- LLM grades it as correct / partial / wrong with a one-sentence reason
- Prints a coloured per-question verdict and a final score summary
- Ctrl-C cancels the quiz mid-stream

**`anamne template export <file>`** - dump templates to a portable JSON file
- File is a plain `{name: body}` JSON object - editable by hand or sync-friendly

**`anamne template import <file>`** - merge templates from a JSON file
- Imports keep existing templates and overwrite same-name entries
- Reports counts of newly-added vs replaced

### Tests
- 87 tests, all passing

---

## [0.29.0] — 2026-05-11

### Added - Phase 29

**`anamne quiz`** - LLM-driven Q&A drill
- Picks N random facts and asks the model to write one question + answer each
- `--tag X` restricts to a topic
- Touches every source fact for ACT-R activation
- Useful for spaced-repetition self-review

**`anamne template`** - named text templates
- `template add <name> "<body>"` - store a reusable format string
- `template list` - dump all defined templates
- `template use <name> "<text>"` - render template + remember in one step
- `template remove <name>` - delete a template
- Templates with a single `{placeholder}` substitute the trailing text directly
- Multi-placeholder templates concatenate the trailing text as a suffix
- Storage: `~/.anamne/templates.json` (plain JSON, editable by hand)

### Tests
- 87 tests, all passing

---

## [0.28.0] — 2026-05-11

### Added - Phase 28

**`anamne fact-of-the-day --post-to <url>`** - webhook integration
- POSTs a JSON payload to any URL when a fact is surfaced
- Payload shape: `{id, fact, tags, pinned, text}` where `text` is a
  pre-formatted message
- Works directly with Slack/Discord-style webhook consumers that read `text`
- Designed for daily-cron + chat integration

**`anamne random <N>`** - sample N random facts for review
- Useful for self-quiz, spaced-repetition style memory reinforcement
- `--tag X` restricts the pool by tag
- `--pinned` samples only from pinned facts
- Touches every surfaced fact for ACT-R activation

### Tests
- 87 tests, all passing

---

## [0.27.0] — 2026-05-11

### Added - Phase 27

**`anamne stash`** - quick-jot working memory shorthand
- `anamne stash "investigate webhook double-fire"` - adds a `[stash]`-prefixed
  working memory note (60-minute TTL by default)
- `anamne stash --list` - show all active stash items
- `anamne stash --promote <id>` - promote a stash item to scratchpad with
  the `stash-promoted` tag
- `anamne stash --clear` - delete every active stash item

**`anamne snapshot --html`** - HTML snapshot variant
- Same four sections, rendered as minimal styled HTML
- Pairs with `--output snapshot.html` for sharing in a browser
- Markdown remains the default

### Tests
- 87 tests, all passing

---

## [0.26.0] — 2026-05-11

### Added - Phase 26

**`anamne merge --dry-run`** - preview merge before applying
- Shows proposed merged text + unioned tags, applies nothing
- Lets you iterate on `--llm` rewrites without committing
- Pairs with `anamne diff` for safe deduplication workflows

**`anamne snapshot`** - Markdown memory snapshot
- Four sections: Pinned, Top activation, Recent (7 days), Working
- `--output FILE` to write a `.md` file; otherwise prints to stdout
- `--limit N` caps each section (default 50)
- Ready to paste into a chat or a standup doc

### Tests
- 87 tests, all passing (+1 covering manual merge history breadcrumb)

---

## [0.25.0] — 2026-05-11

### Added - Phase 25

**`anamne backup --keep N`** - backup rotation
- After writing the new backup, prunes older `anamne-backup-*.json` files
- Keeps only the N newest in the target directory
- `--keep 0` (default) preserves the old behavior of unlimited retention
- Makes daily-cron usage trivially safe

**`anamne merge <keep_id> <drop_id>`** - manual fact merge
- Targeted user-driven merge (no clustering, no consolidate dependency)
- Tags are unioned onto the keeper; donor fact is deleted with a `merged_into`
  history breadcrumb pointing back to the keeper
- `--llm` asks the model to write a concise merged sentence; default is
  simple concatenation with `. ` separator
- Faster path than running full `consolidate` when you've already spotted
  the duplicate with `anamne related` or `anamne diff`

### Tests
- 86 tests, all passing

---

## [0.24.0] — 2026-05-11

### Added - Phase 24

**`anamne diff <id1> <id2>`** - side-by-side fact comparison
- Compares text, tags, created, last_used, use_count, ACT-R, pinned status
- Marks if the fact text is exactly identical
- Great companion to `anamne related` for merge/keep decisions

**`anamne fact-of-the-day`** - daily reminder of one durable fact
- Picks one fact at random from pinned + top-20-activation pool
- Touches the chosen fact for ACT-R tracking
- Designed for shell login hooks or daily standup rituals

**`anamne backup`** - timestamped one-shot JSON backup
- Writes `~/.anamne/backups/anamne-backup-YYYYMMDD-HHMMSS.json` by default
- Same shape as `anamne export` JSON, so it round-trips through `import-memory`
- `--dir` overrides the destination directory

### Tests
- 86 tests, all passing

---

## [0.23.0] — 2026-05-11

### Added - Phase 23

**`anamne search-all <query>`** - cross-layer scan
- Returns up to `--limit` results EACH from scratchpad, episodic, and working
- Scratchpad uses ACT-R-ranked hybrid search
- Episodic uses ChromaDB semantic similarity
- Working uses substring + semantic
- Useful when you don't know which layer holds the answer

**`anamne tag-search <prefix>`** - tag prefix lookup
- Case-insensitive prefix match against every tag
- Sorted by frequency (most-used first), with counts
- Helpful for half-remembered tag names

**`anamne shell` tab completion**
- Tab completion on the shell command name via stdlib `readline`
- `re<TAB>` -> `remember`, `s<TAB><TAB>` -> `search/similar/status`
- Silently skipped on platforms without `readline` (e.g. plain Windows console)

### Tests
- 86 tests, all passing

---

## [0.22.0] — 2026-05-11

### Added - Phase 22

**`anamne tail`** - live tail of memory activity
- Polls SQLite every `--interval` seconds (default 5)
- Shows new fact creations (+fact), retrievals (~retr), history events (!hist),
  and working notes (+work)
- `--once` for a single snapshot
- Ctrl-C stops cleanly

**3 new MCP tools (21 total)**
- `related_facts(memory_id, limit)` - semantic neighbors of a fact
- `promote_working(working_id, tags)` - move working note to scratchpad
- `mark_fact(memory_id, note)` - attach audit annotation to fact history

### Tests
- 86 tests, all passing

---

## [0.21.0] — 2026-05-11

### Added - Phase 21

**`anamne shell`** - interactive REPL
- Persistent prompt that runs ANAMNE commands without re-launching the CLI
- Built-in commands: search, similar, remember, journal, working, ask, info,
  history, recent, tags, status, help, exit
- Catches Ctrl-C and EOF gracefully
- Each command operates on the same `DecisionStore` instance, avoiding the
  startup cost of re-opening SQLite + ChromaDB on every command

### Tests
- 86 tests, all passing

---

## [0.20.0] — 2026-05-11

### Added - Phase 20

**`anamne search --json`** - machine-readable search output
- Pipe-friendly version of `anamne search`
- Composes with `--tag`, `--pinned`, `--no-rank`, `--limit`
- `anamne search auth --json | jq '.[].id'`

**`anamne quote <id>`** - copy-paste-ready fact formatter
- `--style plain` (default) - just the fact text
- `--style markdown` - blockquote with id citation
- `--style bullet` - markdown bullet with inline #tags
- Touches the fact for ACT-R activation tracking

**`anamne mark <id> "<note>"`** - audit annotation
- Attaches a free-text note to the fact's history (`change_type='note'`)
- The fact content is NOT modified; only the audit log gains an entry
- Useful for marginalia: "verified 2026-05-11", "linked to ADR-042"
- Visible via `anamne history <id>`

### Fixed
- `test_activation_formula_correctness` now waits 10ms after `touch_facts` to
  avoid t==0 in the ACT-R formula on fast machines (same pattern as the
  earlier `test_activation_increases_with_retrieval` fix)

### Tests
- 86 tests, all passing

---

## [0.19.0] — 2026-05-11

### Added - Phase 19

**`anamne stats --json`** - machine-readable analytics
- Same data as the pretty table view, emitted as JSON
- Includes top-retrieved facts, creation-per-day, top tags
- Pipe-friendly: `anamne stats --json | jq .top_tags`

**`anamne similar --tag X`** - tag-filtered pure-semantic search
- Pure embedding neighbors of free text, restricted to a tag
- Composes naturally with `--limit`

**`anamne suggest-tags <text>`** - preview LLM tag suggestions
- Pulls existing tags from your store so suggestions reuse them when fitting
- Up to N suggestions with `--max` (default 5)
- Prints the suggested `anamne remember "..." --tag X --tag Y` command for copy-paste
- Does NOT store anything - safe preview tool

### Tests
- 86 tests, all passing

---

## [0.18.0] — 2026-05-11

### Added - Phase 18

**`anamne suggest-pins`** - LLM-curated pin suggestions
- Pulls top-N unpinned facts by ACT-R activation (default 20)
- Asks the LLM to pick the ones that look like durable preferences /
  architecture decisions / long-lived constraints
- `--apply` pins the suggestions automatically; otherwise prints only
- Falls back to "top-5 by activation" when no API key is configured

**`anamne related <id> --tag X`** - tag-filtered neighbors
- Restrict semantic neighbors to those carrying a specific tag (repeatable)
- Useful when you want "Python-flavored neighbors of this fact"

**`anamne facts --json`** - machine-readable output
- Emits the same fact rows as JSON instead of pretty text
- Composes with all existing filters (`--tag`, `--pinned`, `--from/--to`, `--sort`)
- Pipe-friendly: `anamne facts --json | jq '.[].id'`

### Fixed
- `anamne profile` now correctly unwraps `LLMResponse.text` instead of calling
  `.strip()` on the response object

### Tests
- 86 tests, all passing

---

## [0.17.0] — 2026-05-11

### Added - Phase 17

**`anamne similar <text>`** - pure-semantic search
- Free-text semantic-only neighbor search (no substring, no ACT-R rerank)
- Complements `anamne search` (hybrid + ranked) when terminology differs

**`anamne promote <working_id>`** - working -> scratchpad promotion
- Promotes a working-memory note into a permanent scratchpad fact
- Removes the original working note (it's now permanent)
- `--tag` adds tags during promotion
- Workflow: jot transient notes in working, promote what matters

**`anamne profile`** - LLM-generated "about me" summary
- Pulls pinned + most-activated facts (up to 30) and asks the LLM to write
  a 3-5 paragraph profile of you, your preferences, your projects
- Falls back to raw fact dump if no API key is configured
- Useful for handing context to a new AI assistant

**New store methods**
- `working_get(work_id)` - fetch a single working note (active or expired)
- `working_delete(work_id)` - delete one working note (SQLite + ChromaDB)
- `promote_working(work_id, tags)` - move note from working to scratchpad

### Tests
- 86 tests, all passing (+6 for working_get/delete/promote)

---

## [0.16.0] — 2026-05-11

### Added - Phase 16

**`anamne timeline`** - chronological view of memory activity
- For each day: facts created, retrievals, history events
- `--days N` controls the lookback window (default 14)
- `--tag X` filters created facts by tag
- Shows up to 3 fact snippets per day with "...and N more" indicator

**`anamne tags`** - lightweight tag listing
- Lists every distinct tag with its fact count
- `--sort count` (default) or `--sort name`
- `--limit N` caps the output (default 50)
- Faster alternative to `anamne tag-stats` when you just want the names

**`anamne export --since YYYY-MM-DD`** - incremental export
- Only items created on/after the given ISO date
- Composes with `--tag`, `--no-episodic`, `--no-working`, `--format`
- Adds a top-level `"since"` field to the JSON payload for traceability

### Tests
- 80 tests, all passing

---

## [0.15.0] — 2026-05-11

### Added - Phase 15

**`anamne related <id>`** - find semantically similar facts
- `anamne related abc123 --limit 5`
- Uses ChromaDB nearest-neighbor search on the source fact's text
- Excludes the source fact from the results
- Calling `related` "touches" the source for ACT-R activation tracking
- Useful for finding hidden duplicates that exact-text dedupe misses

**`anamne tag-rename <old> <new>`** - bulk rename a tag
- `anamne tag-rename pyhton python` - fix typos across all facts
- If a fact already has the new tag, the old tag is just dropped (no duplicate)
- Records a `tag_renamed` row in fact history for every modified fact

**`anamne tag-clear <tag>`** - strip a tag without deleting facts
- Different from `forget-tag` (which deletes the facts themselves)
- `anamne tag-clear deprecated --yes` - bulk-strip with no prompt
- Records a `tag_removed` row in fact history

### Tests
- 80 tests, all passing (+8 covering related/rename/clear)

---

## [0.14.0] — 2026-05-11

### Added - Phase 14

**`anamne facts --from / --to`** - date-range filter
- `anamne facts --from 2026-05-01 --to 2026-05-11` - facts created in the date window
- Either bound is optional; values are ISO `YYYY-MM-DD`
- Composes with `--tag`, `--pinned`, `--sort`, `--limit`

**`anamne ask --layer episodic|scratchpad|working`** - layer-scoped questions
- `anamne ask "postgres" --layer scratchpad` - instant scratchpad search, no LLM
- `anamne ask "current focus" --layer working` - dump active working memory
- `--layer episodic` (default for episodic-only) routes through the Oracle as before
- `anamne ask --stream` streams the Oracle answer token-by-token (same as `recall --stream`)

**`anamne tag-stats`** - tag distribution + co-occurrence analytics
- Top-N tags table (`--top 20` default) with fact counts
- Co-occurrence: for each top tag, lists the tags that appear with it most often
- `--history` adds a monthly facts-tagged breakdown for the top tags
- Useful for spotting clusters and renaming opportunities

### Tests
- 72 tests, all passing

---

## [0.13.0] — 2026-05-11

### Added - Phase 13

**`anamne recall --stream`** - streaming LLM output
- `anamne recall "question" --stream` prints the Oracle answer token-by-token
- Lower latency to first output vs. waiting for full response
- New `OracleAgent.ask_stream()` method using `LLMClient.complete_stream()`
- New `LLMClient.complete_stream()` generator: Anthropic `messages.stream()` +
  Gemini `models.generate_content_stream()`

**`anamne dedupe`** - exact-text duplicate detection (no LLM)
- `anamne dedupe` shows exact-text duplicates (normalized, case-insensitive)
- Keeps the oldest copy, proposes deleting the rest
- `--yes` to auto-delete; `--min-length N` to skip very short facts
- No API key needed — pure string matching

**`anamne working --extend <id>:<minutes>`** - extend expiry of a working note
- `anamne working --extend abc123:60` adds 60 minutes to the note's expiry
- Extends from whichever is later: current expiry or now

### Fixed
- `test_activation_increases_with_retrieval`: was flaky due to sub-microsecond
  timestamp resolution causing `t == 0`; fixed with explicit 10ms sleep

### Tests
- 72 tests, all passing (flaky test fix applied)

---

## [0.12.0] — 2026-05-11

### Added - Phase 12

**`anamne recap`** - LLM narrative of today's memory activity
- `anamne recap` - one-paragraph summary of what you worked on today
- `anamne recap --days 7` - recap the last week
- `anamne recap --no-llm` - raw dump of new/accessed/working facts without LLM call
- Pulls: facts created today, facts retrieved today (from retrieval_log), active working memory
- LLM writes a human-readable narrative covering decisions, captured context, session focus

**`anamne export --tag <tag>`** - tag-scoped export
- `anamne export --tag python --output python-facts.json`
- Exports only scratchpad facts matching the given tag(s)
- Automatically sets --no-episodic --no-working (tag filter is scratchpad-only)
- Pinned facts get `[PINNED]` marker in Markdown export

**`anamne facts --sort activation|created`**
- `--sort activation` - sort by ACT-R score, most-active first
- `--sort created` - sort by creation date, newest first (same as `anamne recent`)
- Default remains `recency` (last-used-at)

### Tests
- 72 tests, all passing

---

## [0.11.0] — 2026-05-11

### Added - Phase 11

**`anamne recent`** - quick review of the latest additions
- `anamne recent` - show 10 most recently *created* scratchpad facts
- `anamne recent --limit 20 --tag journal` - filter by tag
- Shows creation date prefix, pin indicator, tags inline

**`anamne bulk-tag <tag> <id> [<id>...]`** - batch-apply a tag
- `anamne bulk-tag architecture abc123 def456 ghi789`
- Adds the tag to each fact's existing tags (non-destructive)
- Reports how many were found / not found

**`--pinned` flag on `facts` and `search`**
- `anamne facts --pinned` - list only pinned facts
- `anamne search "deploy" --pinned` - search only within pinned facts

### Tests
- 72 tests, all passing

---

## [0.10.0] — 2026-05-11

### Added - Phase 10

**`anamne pin` / `anamne unpin`** - protect facts from auto-consolidation
- `anamne pin <id>` marks a fact as permanent; it will never be touched by
  `anamne consolidate`, `anamne watch`, or the `consolidate_facts` MCP tool
- `anamne unpin <id>` removes the protection
- `anamne info <id>` shows the pinned status
- `anamne facts` and `anamne search` display `[pin]` indicator for pinned facts
- Web UI: pinned facts show a 📌 icon in the Scratchpad table
- Database migration: adds `pinned INTEGER NOT NULL DEFAULT 0` column to
  the `scratchpad` table on first run (safe ALTER TABLE, existing data unaffected)

**`pin_fact` / `unpin_fact` MCP tools** (18 tools total)
- `pin_fact(memory_id)` / `unpin_fact(memory_id)` — callable from Claude/Cursor
- Useful when an AI assistant identifies a key constraint it should preserve

**`anamne consolidate` / watch daemon skip pinned facts**
- `OracleAgent.consolidate_facts()` now filters out pinned facts before clustering
- Pinned facts are invisible to the consolidation LLM

### Tests
- 72 tests (was 66), all passing
- 7 new pin/unpin tests: pin sets flag, unpin clears it, missing IDs return False,
  list_facts includes pinned field, pinned facts excluded from consolidation input

---

## [0.9.0] — 2026-05-11

### Added - Phase 9

**Graph click-through** (`anamne ui`)
- Clicking a fact node in the Fact Graph tab now opens its change-history modal
- Uses click vs drag detection (< 4px movement = click, larger = drag)
- Legend updated: "Click fact for history · Drag to reposition"

**`anamne reminder`** - time-bound working-memory notes
- `anamne reminder "check build logs" --in 30` - note expires in 30 minutes
- `anamne reminder "standup" --at 09:30` - note expires at 09:30 today (tomorrow if past)
- Default: 60 minutes if neither `--in` nor `--at` is given
- Reminder text is prefixed with `[reminder]` so it stands out in working memory

**`anamne forget-tag <tag>`** - bulk-delete all facts with a tag
- Preview list (first 10 facts) before confirmation
- `--yes` flag to skip prompt for scripting
- Handy for wiping an entire web-import batch (`anamne forget-tag docs.example.com`)

### Tests
- 66 tests, all passing

---

## [0.8.0] — 2026-05-11

### Added - Phase 8

**`anamne import-web --crawl`** - site-wide web crawl
- `anamne import-web https://docs.example.com --crawl --max-pages 30`
- BFS crawler follows same-domain links using stdlib `html.parser` + `urllib.parse` (zero new deps)
- Deduplicates facts across pages: checks both store contents and facts already extracted this session
- Per-page progress display `[1/30] url`
- `--max-pages` cap (default: 20) prevents runaway crawls
- `--limit` still controls max facts extracted *per page*

**Fact Graph tab in web dashboard** (`anamne ui`)
- New "Fact Graph" tab in the local web dashboard
- Force-directed SVG visualization - bipartite layout: fact nodes (blue circles) + tag nodes (orange squares)
- Pure vanilla JS force simulation (repulsion + spring + gravity + damping) - zero external deps, no D3
- Edges connect each fact to its tags; tags with 2+ facts become hub nodes revealing topic clusters
- Hover tooltip showing full fact text or tag member count
- Drag-to-reposition any node; 400-frame animation then settles
- New `/api/graph` endpoint returning `{nodes, edges}` JSON
- Tags appearing on only one fact are excluded (keeps graph readable)

**`anamne stats`** - deep memory analytics command
- `anamne stats` shows detailed statistics beyond `anamne status`
- Most-accessed facts: top 5 by retrieval count with ACT-R score
- Total retrieval count, facts-ever-accessed, average ACT-R activation
- Facts-added-per-day histogram for the last 14 days (ASCII bar chart)
- Oldest and newest scratchpad facts with creation date
- Tag distribution table: top 15 tags by fact count with percentage share
- Direct SQLite queries on `retrieval_log` and `scratchpad` tables

### Tests
- 66 tests, all passing (Phase 8 features are UI/CLI-level, tested manually)

---

## [0.7.0] — 2026-05-11

### Added - Phase 7

**Tag auto-suggest** (`--auto-tag` flag on `remember`)
- `anamne remember "some fact" --auto-tag` - LLM proposes 1-4 tags based on content
- Learns from existing tags already in use for consistency
- Works with `--distill` too: each extracted fact gets auto-tagged individually
- Ignored when `--tag` is already provided (manual tags take precedence)
- New `OracleAgent.suggest_tags(fact)` method

**`anamne watch-repos`** - auto-sync daemon for git repos
- `anamne watch-repos ./frontend ./backend --interval 120`
- Polls repos on a schedule, calls incremental sync only when new commits detected
- Validates paths upfront; skips non-git directories with a warning
- Reports per-repo commit deltas and total indexed count

**Enhanced `status` command**
- Now shows a **Top tags** row: `python:12  db:7  ops:5  (+3 untagged)`
- Quick overview of how your scratchpad is organized without running `facts`

### Tests
- 66 tests total, all passing
- (watch-repos and auto-tag are CLI-level features tested manually)

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
