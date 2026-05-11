"""
anamne CLI - Brain-inspired personal memory layer for AI tools.

Episodic memory:
  init              - interactive setup wizard (picks model, writes .env, indexes)
  index             - read git history and build the episodic knowledge graph
  sync              - incremental re-index (only new commits since last run)
  ask               - cross-layer recall with citations (LIGHT + ACC)
  status            - show knowledge base stats

Scratchpad (durable facts):
  remember          - store a fact; --distill uses LLM to extract many from long text
  search            - search facts (no API key required, hybrid ACT-R ranked)
  recall            - full cross-layer recall (needs API key)
  info              - show full detail + ACT-R score for one fact
  tag               - add/remove/set tags on an existing fact
  forget            - delete a specific fact
  facts             - list all scratchpad facts (supports --tag, --pinned)
  recent            - most recently added facts, newest first
  bulk-tag          - apply a tag to multiple facts at once
  journal           - timestamped journal entry
  import-chat       - extract facts from exported AI conversations
  capture-clipboard - save clipboard text as a fact
  consolidate       - merge redundant facts with LLM
  export            - backup all memories to JSON or Markdown

Working memory (session-scoped):
  working           - add/list/clear short-lived context notes

Maintenance:
  stats             - detailed memory analytics (most-accessed, creation rate, ACT-R)
  tag-stats         - tag analytics: counts, co-occurrence, monthly growth
  recap             - LLM narrative of today's memory activity (--days, --no-llm)
  dedupe            - find and remove exact-text duplicate facts (no LLM required)
  pin               - protect a fact from auto-consolidation
  unpin             - remove pin from a fact
  reminder          - schedule a working-memory note to expire at a given time
  forget-tag        - bulk-delete all facts carrying a specific tag
  clear             - wipe an entire memory layer (scratchpad|working|episodic|all)
  watch             - auto-consolidation daemon (runs periodically)

Server:
  mcp               - start MCP server for Cursor / Claude Code
  mcp-server        - alias for mcp
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

def _version_callback(value: bool) -> None:
    if value:
        from anamne import __version__
        console = Console()
        console.print(f"[bold green]anamne[/bold green] {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="anamne",
    help="[bold green]ANAMNE[/bold green] - Brain-inspired personal memory layer for AI tools.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass

console = Console()

_BANNER = """[bold green]
+---------------------------------------+
|   A N A M N E                        |
|   Brain-inspired personal memory      |
|   layer for AI tools.                 |
+---------------------------------------+[/bold green]"""


def _require_api_key() -> None:
    from anamne.config import get_settings
    cfg = get_settings()
    has_claude = bool(cfg.anthropic_api_key and cfg.anthropic_api_key != "your-key-here")
    has_gemini = bool(cfg.gemini_api_key)
    if not (has_claude or has_gemini):
        console.print(
            "\n[red bold]No LLM API key configured.[/red bold]\n"
            "  Quickest fix: run [bold]anamne init[/bold]\n"
            "  Or manually add one of these to a [bold].env[/bold] file:\n"
            "    [cyan]ANTHROPIC_API_KEY=sk-ant-...[/cyan]  (Claude, paid)\n"
            "    [cyan]GEMINI_API_KEY=...[/cyan]            (Gemini, free tier)\n"
        )
        raise typer.Exit(1)


# ------------------------------------------------------------------ #
# Commands                                                             #
# ------------------------------------------------------------------ #

@app.command()
def init(
    repo: Optional[Path] = typer.Argument(
        None, help="Repository path (default: current directory)"
    ),
    skip_index: bool = typer.Option(
        False, "--skip-index", help="Skip auto-indexing the current repo"
    ),
) -> None:
    """Interactive setup wizard. Picks a model, writes .env, indexes the repo."""
    console.print(_BANNER)

    from anamne.config import get_settings
    cfg = get_settings()
    repo_path = (repo or Path.cwd()).resolve()

    # 1. Detect current model situation
    console.print("\n[bold]Step 1/3 - Detecting available LLM[/bold]")
    if cfg.anthropic_api_key:
        console.print("[green]Found[/green] Anthropic key - will use [cyan]Claude Sonnet 4.6[/cyan] (best quality)")
    elif cfg.gemini_api_key:
        console.print("[green]Found[/green] Gemini key - will use [cyan]Gemini 2.5 Flash[/cyan] (free tier)")
    else:
        console.print("[yellow]No API key found.[/yellow] Two options:\n")
        console.print("  [bold]1[/bold]  Gemini 2.5 Flash Lite  [green](free tier - recommended)[/green]")
        console.print("     -> Sign in at [link]https://aistudio.google.com/apikey[/link]")
        console.print("  [bold]2[/bold]  Claude Sonnet 4.6       [dim](best quality, paid)[/dim]")
        console.print("     -> Get a key at [link]https://platform.anthropic.com[/link]\n")
        choice = typer.prompt("Pick 1 or 2", default="1").strip()
        chosen = {"1": "gemini", "2": "claude"}.get(choice, "gemini")

        env_file = Path(".env")
        existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

        if chosen == "claude":
            console.print(
                "[dim]Tip: keys are visible while typing so you can verify the paste worked. "
                "Press Enter when done.[/dim]"
            )
            key = typer.prompt("Paste your Anthropic API key (sk-ant-...)").strip()
            if not key.startswith("sk-ant-") or len(key) < 20:
                console.print("[red]That doesn't look like a valid Anthropic key. Aborting.[/red]")
                raise typer.Exit(1)
            existing += f"\nANTHROPIC_API_KEY={key}\n"
        else:
            console.print(
                "[dim]Tip: keys are visible while typing so you can verify the paste worked. "
                "Press Enter when done.[/dim]"
            )
            key = typer.prompt("Paste your Gemini API key (AIza...)").strip()
            if not key.startswith("AIza") or len(key) < 20:
                console.print("[red]That doesn't look like a valid Gemini key. Aborting.[/red]")
                raise typer.Exit(1)
            existing += f"\nGEMINI_API_KEY={key}\n"

        env_file.write_text(existing.lstrip() + "\n", encoding="utf-8")
        console.print("[green]Wrote[/green] [bold].env[/bold]")

    # 2. Set up data dir
    console.print("\n[bold]Step 2/3 - Preparing local store[/bold]")
    cfg = get_settings()  # re-read after writing .env
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]OK[/green] Data directory: [dim]{cfg.data_dir}[/dim]")

    # 3. Optionally index the current repo
    console.print("\n[bold]Step 3/3 - Indexing[/bold]")
    if skip_index:
        console.print("[yellow]Skipped (--skip-index).[/yellow]")
        console.print(f"\nRun [bold]anamne index {repo_path}[/bold] when ready.")
        return

    is_git_repo = (repo_path / ".git").exists()
    if not is_git_repo:
        console.print(f"[yellow]Note:[/yellow] [cyan]{repo_path}[/cyan] is not a git repo. Skipping auto-index.")
        console.print("\nRun [bold]anamne index <path-to-repo>[/bold] later.")
        return

    if typer.confirm(f"Index {repo_path} now?", default=True):
        from anamne.agents.historian import HistorianAgent
        from anamne.store.graph import DecisionStore

        store = DecisionStore()
        agent = HistorianAgent(store=store)
        count = agent.index_repo(str(repo_path), max_commits=200)
        console.print(f"\n[bold green]Done[/bold green] - indexed {count} decisions.")

        if count > 0:
            console.print(
                '\nTry it now:\n'
                '  [bold]anamne ask "what was this project built for?"[/bold]'
            )
        else:
            console.print(
                "[yellow]No decisions extracted.[/yellow] "
                "Likely the commit messages are too short or trivial."
            )
    else:
        console.print(f"\nRun [bold]anamne index {repo_path}[/bold] when ready.")


@app.command()
def index(
    repo: Path = typer.Argument(..., help="Path to git repository"),
    max_commits: int = typer.Option(
        500, "--max-commits", "-n", help="Maximum commits to analyse"
    ),
    adr_dir: Optional[Path] = typer.Option(
        None, "--adr-dir", help="Directory containing ADR markdown files"
    ),
) -> None:
    """Index a repository - read git history and build the WHY knowledge graph."""
    _require_api_key()

    from anamne.agents.historian import HistorianAgent
    from anamne.store.graph import DecisionStore

    repo_path = repo.resolve()
    console.print(
        f"\n[bold]Indexing[/bold] [cyan]{repo_path}[/cyan] "
        f"([dim]up to {max_commits} commits[/dim])\n"
    )

    store = DecisionStore()
    agent = HistorianAgent(store=store)

    count = agent.index_repo(str(repo_path), max_commits=max_commits)

    if adr_dir and adr_dir.exists():
        console.print(f"\n[dim]Also indexing ADRs in {adr_dir}...[/dim]")
        count += agent.index_adr_dir(str(adr_dir), repo_path=str(repo_path))

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"Stored [bold]{count}[/bold] new decisions  "
        f"([dim]total: {store.count()}[/dim])\n"
    )

    if count > 0:
        console.print('Try: [bold]anamne ask "why does X exist?"[/bold]')
    else:
        console.print(
            "[yellow]No decisions extracted.[/yellow] "
            "Commits may be too short or trivial."
        )


@app.command()
def sync(
    repo: Path = typer.Argument(..., help="Path to git repository"),
    adr_dir: Optional[Path] = typer.Option(
        None, "--adr-dir", help="Directory containing ADR markdown files"
    ),
) -> None:
    """Incrementally re-index a repository  - only processes new commits.

    Unlike `index`, which always scans all commits, `sync` skips commits
    already processed and only extracts decisions from new ones. Run this
    regularly (e.g. after pushing a batch of commits) to keep episodic
    memory up to date without redundant LLM calls.

    Example:
      anamne sync ./my-project       # after a git pull or git commit
    """
    _require_api_key()
    from anamne.agents.historian import HistorianAgent
    from anamne.store.graph import DecisionStore

    repo_path = repo.resolve()
    store = DecisionStore()
    already_indexed = store.indexed_commit_count(str(repo_path))

    console.print(
        f"\n[bold]Syncing[/bold] [cyan]{repo_path}[/cyan] "
        f"[dim]({already_indexed} commits already indexed)[/dim]\n"
    )

    agent = HistorianAgent(store=store)
    count = agent.index_repo(str(repo_path), max_commits=10_000, incremental=True)

    if adr_dir and adr_dir.exists():
        console.print(f"\n[dim]Also indexing ADRs in {adr_dir}...[/dim]")
        count += agent.index_adr_dir(str(adr_dir), repo_path=str(repo_path))

    if count > 0:
        console.print(
            f"\n[bold green]Done![/bold green] "
            f"Stored [bold]{count}[/bold] new decisions  "
            f"([dim]total: {store.count()}[/dim])\n"
        )
    else:
        console.print("[green]Up to date.[/green] No new decisions found.\n")


@app.command()
def watch(
    interval: int = typer.Option(
        3600, "--interval", "-i",
        help="Seconds between consolidation runs (default: 1 hour)"
    ),
    threshold: float = typer.Option(
        0.6, "--threshold", "-t",
        help="Jaccard similarity threshold for grouping facts (0-1)"
    ),
    min_cluster: int = typer.Option(
        2, "--min-cluster", help="Minimum cluster size to merge"
    ),
) -> None:
    """Periodically auto-consolidate scratchpad facts (memory maintenance daemon).

    Runs `consolidate` on a schedule, merging redundant facts as they accumulate.
    This is the 'sleep-phase consolidation' concept from the ACT-R architecture:
    background maintenance that keeps memory clean and non-redundant over time.

    Press Ctrl+C to stop.

    Examples:
      anamne watch                       # runs every hour
      anamne watch --interval 1800       # every 30 minutes
      anamne watch --threshold 0.5       # more aggressive merging
    """
    import time
    _require_api_key()
    from anamne.agents.oracle import OracleAgent
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    agent = OracleAgent(store=store)

    console.print(
        f"[bold green]Watch mode[/bold green]  - "
        f"consolidating every [bold]{interval}s[/bold]. "
        f"Press [dim]Ctrl+C[/dim] to stop.\n"
    )

    run = 0
    while True:
        run += 1
        fact_count = store.fact_count()

        if fact_count >= min_cluster:
            merges = agent.consolidate_facts(
                similarity_threshold=threshold,
                min_cluster=min_cluster,
                dry_run=False,
            )
            if merges:
                replaced = sum(len(m["replaced"]) for m in merges)
                console.print(
                    f"[dim][run {run}] Merged {replaced} facts into "
                    f"{len(merges)}  - {store.fact_count()} remain[/dim]"
                )
            else:
                console.print(f"[dim][run {run}] {fact_count} facts  - nothing to merge[/dim]")
        else:
            console.print(
                f"[dim][run {run}] Only {fact_count} fact(s)  - "
                f"need {min_cluster}+ to consolidate[/dim]"
            )

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Watch stopped.[/dim]")
            break


@app.command(name="watch-repos")
def watch_repos(
    repos: list[Path] = typer.Argument(
        ..., help="Git repository paths to watch (space-separated)"
    ),
    interval: int = typer.Option(
        300, "--interval", "-i",
        help="Seconds between sync checks (default: 5 min)"
    ),
    max_commits: int = typer.Option(
        50, "--max-commits", help="Max commits per sync run"
    ),
) -> None:
    """Watch one or more git repos and auto-sync new commits as they land.

    Polls each repo on a schedule, calling `anamne sync` only when new
    commits are detected. Ideal for running after `git pull` in CI or
    as a background daemon after active development sessions.

    Press Ctrl+C to stop.

    Examples:
      anamne watch-repos ./my-project
      anamne watch-repos ./frontend ./backend --interval 120
    """
    import time as _time

    _require_api_key()
    from anamne.agents.historian import HistorianAgent
    from anamne.store.graph import DecisionStore

    if not repos:
        console.print("[red]Specify at least one repo path.[/red]")
        raise typer.Exit(1)

    # Validate paths upfront
    valid_repos = []
    for rp in repos:
        rp = rp.resolve()
        if not (rp / ".git").exists():
            console.print(f"[yellow]Not a git repo (skipping): {rp}[/yellow]")
        else:
            valid_repos.append(rp)

    if not valid_repos:
        console.print("[red]No valid git repos to watch.[/red]")
        raise typer.Exit(1)

    store = DecisionStore()
    historian = HistorianAgent(store=store)

    repo_labels = ", ".join(str(r) for r in valid_repos)
    console.print(
        f"\n[bold green]Watching repos[/bold green]: {repo_labels}\n"
        f"Polling every [bold]{interval}s[/bold]. Press [dim]Ctrl+C[/dim] to stop.\n"
    )

    # Track commit counts so we can detect new activity
    prev_counts: dict[str, int] = {
        str(r): store.indexed_commit_count(str(r)) for r in valid_repos
    }

    check = 0
    while True:
        check += 1
        synced_any = False
        for rp in valid_repos:
            rp_str = str(rp)
            try:
                from git import Repo as _Repo
                git_repo = _Repo(rp_str)
                # Count total commits in the repo
                total_commits = sum(1 for _ in git_repo.iter_commits())
                indexed = store.indexed_commit_count(rp_str)

                if total_commits > indexed:
                    new_count = total_commits - indexed
                    console.print(
                        f"[cyan]{rp.name}[/cyan]: "
                        f"{new_count} new commit(s) detected  - syncing..."
                    )
                    historian.index_repo(
                        rp_str, max_commits=max_commits, incremental=True
                    )
                    new_indexed = store.indexed_commit_count(rp_str)
                    delta = new_indexed - indexed
                    console.print(
                        f"  [green]Indexed {delta} commit(s)[/green] "
                        f"({new_indexed} total)"
                    )
                    synced_any = True
                else:
                    console.print(
                        f"[dim][check {check}] {rp.name}: no new commits[/dim]"
                    )
            except Exception as e:
                console.print(f"[red]Error checking {rp.name}: {e}[/red]")

        if not synced_any:
            pass  # already printed per-repo status above

        try:
            _time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]watch-repos stopped.[/dim]")
            break


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your WHY question about the codebase"),
    layer: Optional[str] = typer.Option(
        None, "--layer", "-l",
        help="Restrict to layers: episodic | scratchpad | working "
             "(combinable with '+', e.g. 'episodic+scratchpad')"
    ),
    stream: bool = typer.Option(
        False, "--stream", "-s",
        help="Stream LLM answer token-by-token"
    ),
) -> None:
    """Ask a question - recalls across all three memory layers with citations.

    Use --layer to restrict to one or more memory layers:
      episodic    - only git/ADR decisions
      scratchpad  - only durable facts (no LLM needed alone)
      working     - only active session notes (no LLM needed alone)

    Combine layers with '+' to do a hybrid scan:
      episodic+scratchpad   - skip working memory
      scratchpad+working    - skip episodic (no LLM)
      episodic+working      - skip scratchpad

    Use --stream for streaming LLM output (lower latency to first token).

    Examples:
      anamne ask "why did we choose PostgreSQL?"
      anamne ask "what DB tech do we use?" --layer scratchpad
      anamne ask "what's in my head right now?" --layer scratchpad+working
      anamne ask "architecture overview" --stream
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    layer_norm = (layer or "").lower().strip()
    layers_req = (
        {p.strip() for p in layer_norm.split("+") if p.strip()}
        if layer_norm else set()
    )
    valid_layers = {"episodic", "scratchpad", "working"}
    invalid = layers_req - valid_layers
    if invalid:
        console.print(
            f"[red]Unknown layer(s): {', '.join(invalid)}[/red]  - "
            "choose from: episodic | scratchpad | working"
        )
        raise typer.Exit(1)

    # Single-layer non-LLM shortcuts (preserve old behavior)
    if layers_req == {"scratchpad"}:
        results = store.search_facts_ranked(question, limit=10)
        if not results:
            console.print("[dim]No matching scratchpad facts.[/dim]")
            return
        console.print(f"\n[bold cyan]Scratchpad facts matching '{question}':[/bold cyan]\n")
        for f in results:
            tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
            console.print(f"  - {f['fact']}{tag_str}")
        console.print()
        return

    if layers_req == {"working"}:
        items = store.working_active()
        if not items:
            console.print("[dim]Working memory is empty.[/dim]")
            return
        console.print(f"\n[bold cyan]Active working memory ({len(items)} notes):[/bold cyan]\n")
        for w in items:
            console.print(f"  [dim]{w['id']}[/dim]  {w['note']}")
            console.print(f"           [dim]expires: {w['expires_at']}[/dim]")
        console.print()
        return

    # Compound layer filter without episodic - still no LLM needed
    if layers_req == {"scratchpad", "working"}:
        scratch = store.search_facts_ranked(question, limit=10)
        work = store.search_working(question, limit=10)
        if not (scratch or work):
            console.print("[dim]No matching scratchpad or working entries.[/dim]")
            return
        console.print(
            f"\n[bold cyan]Scratchpad + Working matches for '{question}':[/bold cyan]\n"
        )
        if scratch:
            console.print("  [bold]Scratchpad[/bold]")
            for f in scratch:
                tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
                console.print(f"    - {f['fact']}{tag_str}")
        if work:
            console.print("  [bold]Working[/bold]")
            for w in work:
                console.print(f"    - {w['note']}")
        console.print()
        return

    _require_api_key()
    from anamne.agents.oracle import OracleAgent

    agent = OracleAgent(store=store)
    if stream:
        agent.ask_stream(question)
    else:
        agent.ask_pretty(question)


# ------------------------------------------------------------------ #
# Memory layer commands (v0.2  - brain-inspired)                        #
# ------------------------------------------------------------------ #

@app.command()
def remember(
    fact: str = typer.Argument(..., help="A fact (or long block) to remember"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tags (repeatable)"),
    distill: bool = typer.Option(
        False, "--distill", "-d",
        help="Use LLM to extract multiple structured facts from long input "
             "(LIGHT-style key-value distillation)"
    ),
    auto_tag: bool = typer.Option(
        False, "--auto-tag", "-a",
        help="Ask the LLM to suggest tags automatically (uses API key)"
    ),
) -> None:
    """Store a fact in scratchpad memory.

    Short text -> stored verbatim.
    Long text + --distill -> LLM extracts multiple structured facts.
    --auto-tag -> LLM suggests tags (ignored if --tag is already provided).

    Examples:
      anamne remember "I prefer Postgres over MySQL"
      anamne remember "I prefer Postgres over MySQL" --auto-tag
      anamne remember "I prefer Postgres over MySQL" --tag db --tag backend
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if distill:
        _require_api_key()
        from anamne.llm import LLMClient
        llm = LLMClient()
        prompt = (
            "Extract durable, atomic facts from the text below. Each fact "
            "should be a single self-contained statement that's still useful "
            "weeks from now. Skip filler, opinions, and ephemeral details.\n\n"
            f"Text:\n{fact}\n\n"
            "Return ONLY a JSON array of strings. Example:\n"
            '["I prefer Python over Go", "I work in Pacific time zone"]\n\n'
            "JSON array:"
        )
        try:
            import json
            raw = llm.complete(prompt, max_tokens=512).text.strip()
            # Strip code fence if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            extracted = json.loads(raw)
            if not isinstance(extracted, list):
                raise ValueError("Expected JSON array")
        except Exception as e:
            console.print(f"[yellow]Distill failed ({e}), storing as one fact.[/yellow]")
            extracted = [fact]

        for f in extracted:
            final_tags = list(tag)
            if auto_tag and not tag:
                _require_api_key()
                from anamne.agents.oracle import OracleAgent
                suggested = OracleAgent(store=store).suggest_tags(f.strip())
                final_tags = suggested
                if suggested:
                    console.print(f"[dim]  auto-tags: {', '.join(suggested)}[/dim]")
            mem_id = store.remember(f.strip(), tags=final_tags or None)
            console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]: {f}")
        console.print(f"\n[dim]Stored {len(extracted)} fact(s) from input.[/dim]")
    else:
        final_tags = list(tag)
        if auto_tag and not tag:
            _require_api_key()
            from anamne.agents.oracle import OracleAgent
            console.print("[dim]Suggesting tags...[/dim]")
            suggested = OracleAgent(store=store).suggest_tags(fact)
            final_tags = suggested
            if suggested:
                console.print(f"[dim]  auto-tags: {', '.join(suggested)}[/dim]")
        mem_id = store.remember(fact, tags=final_tags or None)
        console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]: {fact}")
        if final_tags:
            console.print(f"[dim]  tags: {', '.join(final_tags)}[/dim]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="What to recall from memory"),
    stream: bool = typer.Option(
        False, "--stream", "-s",
        help="Stream the LLM answer token-by-token as it arrives"
    ),
) -> None:
    """Recall across episodic memory and scratchpad facts.

    With --stream, the LLM answer is printed character-by-character as it
    arrives (lower latency to first token, useful for long answers).

    Examples:
      anamne recall "why did we switch databases?"
      anamne recall "payment architecture" --stream
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    # Scratchpad  - ACT-R ranked, no LLM call needed
    facts = store.search_facts_ranked(query, limit=5)
    if facts:
        console.print("\n[bold cyan]From scratchpad:[/bold cyan]")
        for f in facts:
            tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
            console.print(f"  - {f['fact']}{tag_str}")

    # Episodic memory  - uses Oracle agent
    if store.count() > 0:
        _require_api_key()
        from anamne.agents.oracle import OracleAgent
        console.print("\n[bold cyan]From episodic memory:[/bold cyan]")
        agent = OracleAgent(store=store)
        if stream:
            agent.ask_stream(query)
        else:
            agent.ask_pretty(query)
    elif not facts:
        console.print(
            "\n[yellow]Nothing found.[/yellow] "
            "Try [bold]anamne remember[/bold] or [bold]anamne index[/bold] first."
        )


@app.command()
def forget(
    memory_id: str = typer.Argument(..., help="Scratchpad memory ID to delete"),
) -> None:
    """Forget a specific scratchpad fact."""
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    if store.forget_fact(memory_id):
        console.print(f"[green]Forgot[/green] {memory_id}")
    else:
        console.print(f"[yellow]No fact with id {memory_id}[/yellow]")


@app.command()
def prune(
    older_than: Optional[str] = typer.Option(
        None, "--older-than", "-o", metavar="YYYY-MM-DD",
        help="Delete facts created before this date"
    ),
    no_retrievals_since: Optional[str] = typer.Option(
        None, "--no-retrievals-since", "-r", metavar="YYYY-MM-DD",
        help="Delete facts with NO retrieval since this date "
             "(unused-and-stale)"
    ),
    tag: list[str] = typer.Option(
        [], "--tag", "-t",
        help="Restrict to facts with this tag (repeatable)"
    ),
    keep_pinned: bool = typer.Option(
        True, "--keep-pinned/--no-keep-pinned",
        help="Skip pinned facts (default: yes)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Bulk-prune stale scratchpad facts older than a given ISO date.

    Pinned facts are preserved by default (use `--no-keep-pinned` to override).
    Tag filters apply on top of the date cutoff. Dry-run preview is shown
    before confirmation unless `--yes` is given.

    Examples:
      anamne prune --older-than 2025-01-01
      anamne prune --older-than 2026-01-01 --tag journal --yes
      anamne prune --older-than 2024-12-31 --no-keep-pinned
      anamne prune --no-retrievals-since 2026-01-01     # unused facts
    """
    import sqlite3
    from anamne.store.graph import DecisionStore

    if not older_than and not no_retrievals_since:
        console.print(
            "[red]Provide at least one cutoff: "
            "--older-than YYYY-MM-DD or --no-retrievals-since YYYY-MM-DD.[/red]"
        )
        raise typer.Exit(code=1)

    store = DecisionStore()
    candidates = store.list_facts(limit=100_000, tags=tag or None)
    if older_than:
        candidates = [f for f in candidates if (f.get("created_at") or "") < older_than]

    if no_retrievals_since:
        # A fact qualifies if it has NO retrieval >= the cutoff.
        with sqlite3.connect(store._db) as con:
            try:
                rows = con.execute(
                    "SELECT DISTINCT fact_id FROM retrieval_log "
                    "WHERE retrieved_at >= ?",
                    (no_retrievals_since,),
                ).fetchall()
                recently_touched = {r[0] for r in rows}
            except Exception:
                recently_touched = set()
        candidates = [f for f in candidates if f["id"] not in recently_touched]

    if keep_pinned:
        candidates = [f for f in candidates if not f.get("pinned")]

    if not candidates:
        console.print(
            f"\n  [dim]Nothing to prune"
            + (f" older than {older_than}" if older_than else "")
            + (f" / no retrievals since {no_retrievals_since}"
                if no_retrievals_since else "")
            + (f", tag={','.join(tag)}" if tag else "")
            + (" (pinned kept)" if keep_pinned else "")
            + ".[/dim]\n"
        )
        return

    label_parts = []
    if older_than:
        label_parts.append(f"created before {older_than}")
    if no_retrievals_since:
        label_parts.append(f"no retrievals since {no_retrievals_since}")
    label = " AND ".join(label_parts)

    console.print(
        f"\n  [yellow]Would delete {len(candidates)} fact(s) "
        f"({label})"
        + (f", tag={','.join(tag)}" if tag else "")
        + (" (pinned preserved)" if keep_pinned else "")
        + ".[/yellow]\n"
    )
    for f in candidates[:10]:
        console.print(f"  [dim]{f['id']}  {(f.get('created_at') or '')[:10]}[/dim]  "
                      f"{f['fact'][:80]}")
    if len(candidates) > 10:
        console.print(f"  [dim]... and {len(candidates) - 10} more[/dim]")
    console.print()

    if not yes:
        if not typer.confirm(f"Delete {len(candidates)} fact(s)?", default=False):
            console.print("[dim]Cancelled.[/dim]\n")
            return

    deleted = 0
    for f in candidates:
        try:
            if store.forget_fact(f["id"]):
                deleted += 1
        except Exception:
            pass
    console.print(f"\n  [green]Pruned {deleted} fact(s).[/green]\n")


@app.command()
def pin(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to pin"),
) -> None:
    """Pin a fact so it is never touched by auto-consolidation.

    Pinned facts are excluded from `anamne consolidate` and `anamne watch`.
    Use this for critical facts that must never be merged, reworded, or deleted
    automatically — architecture decisions, hard constraints, etc.

    The pin can be removed with `anamne unpin <id>`.

    Examples:
      anamne pin abc123def456
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    if store.pin_fact(memory_id):
        console.print(f"[green]Pinned[/green] {memory_id}  "
                      f"[dim](protected from auto-consolidation)[/dim]")
    else:
        console.print(f"[yellow]No fact with id {memory_id}[/yellow]")


@app.command()
def unpin(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to unpin"),
) -> None:
    """Remove the pin from a fact, allowing auto-consolidation to consider it again.

    Examples:
      anamne unpin abc123def456
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    if store.unpin_fact(memory_id):
        console.print(f"[dim]Unpinned[/dim] {memory_id}  "
                      f"[dim](fact is now eligible for auto-consolidation)[/dim]")
    else:
        console.print(f"[yellow]No fact with id {memory_id}[/yellow]")


@app.command()
def quote(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to format"),
    style: str = typer.Option("plain", "--style", "-s",
                              help="Format: plain | markdown | bullet"),
) -> None:
    """Print a fact formatted for copy-paste into a chat or document.

    Useful when you want to drop a stored fact into a Claude/Cursor/ChatGPT
    conversation without retyping it. Touches the fact for ACT-R tracking.

    Styles:
      plain    - just the fact text, no formatting
      markdown - quoted block with id citation
      bullet   - markdown list item with tags inline

    Examples:
      anamne quote abc123
      anamne quote abc123 --style markdown
      anamne quote abc123 --style bullet
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    fact = store.get_fact(memory_id)
    if fact is None:
        console.print(f"[red]No fact found with id '{memory_id}'.[/red]")
        raise typer.Exit(code=1)

    text = fact["fact"]
    tags = fact.get("tags") or []
    if style == "markdown":
        output = f"> {text}\n>\n> — *anamne fact `{memory_id}`*"
    elif style == "bullet":
        tag_str = (" [" + ", ".join(f"#{t}" for t in tags) + "]") if tags else ""
        output = f"- {text}{tag_str}"
    else:  # plain
        output = text

    # Print plain to stdout - no Rich markup so it's pipeable
    print(output)
    try:
        store.touch_facts([memory_id])
    except Exception:
        pass


@app.command()
def mark(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to annotate"),
    note: str = typer.Argument(..., help="Short note to attach as a history event"),
) -> None:
    """Attach a free-text note to a fact's audit history (without changing content).

    The note shows up in `anamne history <id>` as a `note` change_type entry.
    Useful for marginalia: "verified 2026-05-11" or "see also #1234".

    Examples:
      anamne mark abc123 "verified after 2026-05-01 review"
      anamne mark abc123 "linked to ADR-042"
    """
    import sqlite3
    from datetime import datetime, timezone
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    fact = store.get_fact(memory_id)
    if fact is None:
        console.print(f"[red]No fact found with id '{memory_id}'.[/red]")
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(store._db) as con:
        con.execute(
            "INSERT INTO fact_history "
            "(fact_id, content, tags, changed_at, change_type, merged_into) "
            "VALUES (?, ?, ?, ?, 'note', NULL)",
            (memory_id, note, json.dumps(fact["tags"]), now),
        )
    console.print(f"\n  [green]Marked[/green] [cyan]{memory_id}[/cyan]  -  {note}\n")


@app.command()
def info(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to inspect"),
) -> None:
    """Show full details of a scratchpad fact, including ACT-R activation score.

    Example:
      anamne info abc123def456
    """
    from anamne.store.graph import DecisionStore
    from rich.table import Table

    store = DecisionStore()
    fact = store.get_fact(memory_id)

    if fact is None:
        console.print(f"[red]No fact found with id:[/red] {memory_id}")
        raise typer.Exit(1)

    table = Table(
        border_style="cyan", show_header=False, padding=(0, 2),
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("ID", fact["id"])
    table.add_row("Fact", fact["fact"])
    table.add_row("Tags", ", ".join(fact["tags"]) if fact["tags"] else "(none)")
    table.add_row("Created", fact["created_at"])
    table.add_row("Last used", fact["last_used_at"])
    table.add_row("Use count", str(fact["use_count"]))
    table.add_row(
        "ACT-R activation",
        f"{fact['activation']:.4f}" if fact["activation"] else "0.0 (never retrieved)",
    )
    table.add_row(
        "Pinned",
        "[green]YES (protected from auto-consolidation)[/green]" if fact.get("pinned")
        else "[dim]no[/dim]",
    )

    console.print()
    console.print(table)
    console.print()


@app.command()
def tag(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID"),
    add: list[str] = typer.Option([], "--add", "-a", help="Tag to add (repeatable)"),
    remove: list[str] = typer.Option([], "--remove", "-r", help="Tag to remove (repeatable)"),
    set_: list[str] = typer.Option(
        [], "--set", "-s", help="Replace ALL tags with these (repeatable)"
    ),
) -> None:
    """Add, remove, or replace tags on an existing scratchpad fact.

    Examples:
      anamne tag abc123 --add python --add backend
      anamne tag abc123 --remove deprecated
      anamne tag abc123 --set python --set testing   # replaces all tags
    """
    if not (add or remove or set_):
        # Show current tags if no operation specified
        from anamne.store.graph import DecisionStore
        fact = DecisionStore().get_fact(memory_id)
        if fact is None:
            console.print(f"[red]No fact with id {memory_id}[/red]")
            raise typer.Exit(1)
        tags = fact["tags"]
        console.print(f"Tags on [cyan]{memory_id}[/cyan]: {', '.join(tags) if tags else '(none)'}")
        return

    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    new_tags = store.update_fact_tags(
        memory_id,
        add=add or None,
        remove=remove or None,
        set_tags=set_ or None,
    )

    if new_tags is None:
        console.print(f"[red]No fact with id {memory_id}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]Updated[/green] [cyan]{memory_id}[/cyan]  - "
        f"tags: {', '.join(new_tags) if new_tags else '(none)'}"
    )


@app.command()
def edit(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID to edit"),
    content: str = typer.Argument(..., help="New content for the fact"),
) -> None:
    """Update the text content of a scratchpad fact (old version is preserved in history).

    Example:
      anamne edit abc123def456 "Corrected fact text here"
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    updated = store.update_fact_content(memory_id, content)
    if updated:
        console.print(f"[green]Updated[/green] [cyan]{memory_id}[/cyan]")
        console.print(f"  New content: {content}")
    else:
        console.print(f"[red]No fact found with id:[/red] {memory_id}")
        raise typer.Exit(1)


@app.command()
def history(
    memory_id: str = typer.Argument(..., help="Scratchpad fact ID"),
) -> None:
    """Show the full change history of a scratchpad fact.

    Records every create, edit, tag change, and deletion (including merges).
    Useful for auditing what happened to a fact over time.

    Example:
      anamne history abc123def456
    """
    from anamne.store.graph import DecisionStore
    from rich.table import Table

    store = DecisionStore()
    events = store.get_fact_history(memory_id)

    if not events:
        console.print(
            f"[yellow]No history found for[/yellow] [cyan]{memory_id}[/cyan] "
            "(fact may have been created before versioning was enabled)"
        )
        return

    table = Table(title=f"History for {memory_id}", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("When", style="yellow", no_wrap=True)
    table.add_column("Change", style="cyan", width=16)
    table.add_column("Content", no_wrap=False)
    table.add_column("Tags", width=20)
    table.add_column("Merged->", width=14)

    _type_color = {
        "created": "green",
        "content_updated": "yellow",
        "tags_updated": "blue",
        "forgotten": "red",
        "merged_into": "magenta",
    }

    for i, ev in enumerate(events, 1):
        c = _type_color.get(ev["change_type"], "white")
        tags_str = ", ".join(ev["tags"]) if ev["tags"] else "(none)"
        merged_str = ev["merged_into"] or ""
        table.add_row(
            str(i),
            ev["changed_at"][:19].replace("T", " "),
            f"[{c}]{ev['change_type']}[/{c}]",
            ev["content"][:80] + ("..." if len(ev["content"]) > 80 else ""),
            tags_str,
            merged_str[:12] if merged_str else "",
        )

    console.print()
    console.print(table)
    console.print()


@app.command()
def consolidate(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview merges without writing anything"
    ),
    threshold: float = typer.Option(
        0.6, "--threshold", "-t",
        help="Jaccard similarity threshold for grouping facts (0-1)"
    ),
    min_cluster: int = typer.Option(
        2, "--min-cluster", help="Minimum cluster size to merge"
    ),
) -> None:
    """Merge redundant scratchpad facts using LLM consolidation.

    Scans your scratchpad for semantically similar facts, groups them,
    and merges each group into a single clean statement. Inspired by the
    Agent Cognitive Compressor (ACC) paper's bounded-state design and the
    brain's sleep-phase memory consolidation.

    Use --dry-run to preview what would be merged before committing.
    """
    _require_api_key()
    from anamne.agents.oracle import OracleAgent
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    fact_count = store.fact_count()

    if fact_count == 0:
        console.print("[dim]Scratchpad is empty  - nothing to consolidate.[/dim]")
        return

    console.print(
        f"\n[bold]Consolidating[/bold] {fact_count} scratchpad facts "
        f"[dim](threshold={threshold})[/dim]...\n"
    )

    agent = OracleAgent(store=store)
    merges = agent.consolidate_facts(
        similarity_threshold=threshold,
        min_cluster=min_cluster,
        dry_run=dry_run,
    )

    if not merges:
        console.print("[green]No redundant fact clusters found.[/green] Scratchpad looks clean.")
        return

    mode_label = "[yellow]DRY RUN[/yellow]  - " if dry_run else ""
    console.print(f"{mode_label}[bold]{len(merges)} merge(s):[/bold]\n")

    for i, m in enumerate(merges, 1):
        console.print(f"[cyan]Merge {i}:[/cyan]")
        for fact in m["replaced_facts"]:
            console.print(f"  [dim]- {fact}[/dim]")
        console.print(f"  [green]-> {m['merged']}[/green]\n")

    if dry_run:
        console.print(
            "[yellow]Dry run  - nothing changed.[/yellow] "
            "Re-run without --dry-run to apply."
        )
    else:
        replaced = sum(len(m["replaced"]) for m in merges)
        console.print(
            f"[green]Done.[/green] Replaced {replaced} facts with {len(merges)} merged fact(s)."
        )


@app.command()
def dedupe(
    yes: bool = typer.Option(False, "--yes", "-y", help="Delete duplicates automatically"),
    min_length: int = typer.Option(
        10, "--min-length",
        help="Only consider facts longer than this many characters"
    ),
) -> None:
    """Find and remove exact-text duplicate scratchpad facts (no LLM required).

    Compares normalized fact text (stripped, lowercased) across all scratchpad
    entries. When duplicates are found, keeps the oldest and removes the rest.

    Unlike `anamne consolidate`, this is purely string-equality matching -
    no LLM call, no API key needed. Run it first as a cheap dedup pass.

    Examples:
      anamne dedupe             # preview duplicates
      anamne dedupe --yes       # delete automatically
    """
    import sqlite3
    from collections import defaultdict
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    with sqlite3.connect(store._db) as con:
        rows = con.execute(
            "SELECT id, fact, created_at FROM scratchpad ORDER BY created_at ASC"
        ).fetchall()

    # Group by normalized text
    groups: dict = defaultdict(list)
    for fid, fact, created in rows:
        if len(fact) >= min_length:
            key = fact.strip().lower()
            groups[key].append((fid, fact, created))

    dupes = {k: v for k, v in groups.items() if len(v) > 1}

    if not dupes:
        console.print(f"[green]No exact duplicates found[/green] across {len(rows)} facts.")
        return

    total_to_delete = sum(len(v) - 1 for v in dupes.values())
    console.print(f"\n  [yellow]Found {len(dupes)} duplicate group(s) "
                  f"({total_to_delete} facts to remove):[/yellow]\n")

    all_ids_to_delete: list[str] = []
    for key, entries in dupes.items():
        keeper = entries[0]  # oldest
        to_delete = entries[1:]
        console.print(f"  [dim]Keep:[/dim]   [{keeper[0]}] {keeper[1][:70]}")
        for fid, fact, _ in to_delete:
            console.print(f"  [red]Delete:[/red] [{fid}] {fact[:70]}")
            all_ids_to_delete.append(fid)
        console.print()

    if not yes:
        if not typer.confirm(
            f"Delete {total_to_delete} duplicate fact(s)?", default=False
        ):
            console.print("[dim]Cancelled.[/dim]")
            return

    deleted = 0
    for fid in all_ids_to_delete:
        if store.forget_fact(fid):
            deleted += 1

    console.print(f"\n  [green]Deleted {deleted} duplicate fact(s).[/green]\n")


@app.command()
def facts(
    limit: int = typer.Option(20, "--limit", "-n", help="How many to list"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag (repeatable)"),
    pinned_only: bool = typer.Option(False, "--pinned", help="Only show pinned facts"),
    sort: str = typer.Option(
        "recency", "--sort", "-s",
        help="Sort order: recency (default) | activation | created"
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", metavar="YYYY-MM-DD", help="Only facts created on or after this date"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of pretty text"
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", metavar="YYYY-MM-DD", help="Only facts created on or before this date"
    ),
) -> None:
    """List facts in scratchpad memory, optionally filtered by tag, date, or pin status.

    Sort options:
      recency    - most recently *used* first (default, ACT-R friendly)
      activation - highest ACT-R activation score first (requires retrievals)
      created    - most recently *created* first (like `anamne recent`)

    Examples:
      anamne facts
      anamne facts --tag python --limit 10
      anamne facts --pinned
      anamne facts --sort activation
      anamne facts --from 2026-05-01 --to 2026-05-11
      anamne facts --from 2026-05-01 --tag journal
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    fetch_limit = limit * 5 if (pinned_only or sort == "activation" or from_date or to_date) else limit
    rows = store.list_facts(limit=fetch_limit, tags=tag or None)

    if pinned_only:
        rows = [f for f in rows if f.get("pinned")]
    if from_date:
        rows = [f for f in rows if (f.get("created_at") or "") >= from_date]
    if to_date:
        # Include full to_date day (compare with day+1 string for ISO sort)
        rows = [f for f in rows if (f.get("created_at") or "") <= to_date + "T23:59:59"]

    if sort == "activation":
        rows = sorted(rows, key=lambda f: store.activation_score(f["id"]), reverse=True)
    elif sort == "created":
        rows = sorted(rows, key=lambda f: f.get("created_at") or "", reverse=True)
    rows = rows[:limit]
    if as_json:
        # Emit a stable JSON shape - useful for piping into jq or shell scripts
        console.print(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        if pinned_only:
            console.print("[dim]No pinned facts. Use [bold]anamne pin <id>[/bold] to protect a fact.[/dim]")
        elif tag:
            console.print(f"[dim]No facts tagged: {', '.join(tag)}[/dim]")
        elif from_date or to_date:
            console.print(f"[dim]No facts in the specified date range.[/dim]")
        else:
            console.print("[dim]Scratchpad is empty. Try [bold]anamne remember \"...\"[/bold][/dim]")
        return
    for f in rows:
        tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
        pin_str = "  [green][pin][/green]" if f.get("pinned") else ""
        date_str = f"  [dim]{f['created_at'][:10]}[/dim]" if (from_date or to_date) else ""
        console.print(f"[cyan]{f['id']}[/cyan]{pin_str}{date_str}  {f['fact']}{tag_str}")


@app.command()
def recent(
    limit: int = typer.Option(10, "--limit", "-n", help="How many to show"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag"),
) -> None:
    """Show the most recently added scratchpad facts (quick journal review).

    Ordered by creation date, newest first. Useful for a quick review of what
    you've captured recently without needing to search.

    Examples:
      anamne recent
      anamne recent --limit 20
      anamne recent --tag journal
    """
    import sqlite3
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    with sqlite3.connect(store._db) as con:
        rows = con.execute(
            "SELECT id, fact, tags, created_at, COALESCE(pinned,0) "
            "FROM scratchpad ORDER BY created_at DESC LIMIT ?",
            (limit * 3 if tag else limit,),
        ).fetchall()

    import json as _json
    results = [
        {
            "id": r[0], "fact": r[1], "tags": _json.loads(r[2]),
            "created_at": r[3], "pinned": bool(r[4]),
        }
        for r in rows
    ]
    if tag:
        tag_set = set(tag)
        results = [f for f in results if tag_set.intersection(f["tags"])]
    results = results[:limit]

    if not results:
        console.print("[dim]No facts found.[/dim]")
        return

    console.print(f"\n[bold]Recent facts[/bold]  ({len(results)} shown):\n")
    for f in results:
        tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f["tags"] else ""
        pin_str = "  [green][pin][/green]" if f.get("pinned") else ""
        date_str = f"[dim]{f['created_at'][:10]}[/dim]  " if f.get("created_at") else ""
        console.print(f"  {date_str}[cyan]{f['id']}[/cyan]{pin_str}  {f['fact']}{tag_str}")
    console.print()


@app.command(name="bulk-tag")
def bulk_tag(
    tag: str = typer.Argument(..., help="Tag to apply"),
    ids: list[str] = typer.Argument(..., help="One or more fact IDs to tag"),
) -> None:
    """Apply a tag to multiple facts at once.

    Useful after an import batch: grab all the new IDs and tag them in one step.
    The tag is added to existing tags (not replacing them).

    Examples:
      anamne bulk-tag architecture abc123 def456 ghi789
      anamne bulk-tag web-import $(anamne facts --tag web-import -n 100 | awk '{print $1}')
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    ok_count = 0
    fail_count = 0
    for fid in ids:
        result = store.update_fact_tags(fid, add=[tag])
        if result is not None:
            ok_count += 1
        else:
            console.print(f"  [yellow]Not found:[/yellow] {fid}")
            fail_count += 1

    if ok_count:
        console.print(f"  [green]Tagged {ok_count} fact(s)[/green] with '[cyan]{tag}[/cyan]'")
    if fail_count:
        console.print(f"  [yellow]{fail_count} ID(s) not found[/yellow]")


@app.command()
def recap(
    days: int = typer.Option(1, "--days", "-d",
                              help="Look back N days (default: 1 = today only)"),
    no_llm: bool = typer.Option(False, "--no-llm",
                                 help="Skip LLM summary, just print raw activity"),
) -> None:
    """Generate an LLM summary of your memory activity for today (or recent days).

    Pulls together:
      - Journal entries added in the period
      - All facts created or updated in the period
      - Working memory notes (active right now)
      - Facts retrieved (accessed) in the period (from retrieval_log)

    Then asks the LLM to write a human-readable summary of what you worked on,
    what you decided, and what facts were reinforced.

    Use --no-llm to print raw activity without calling the LLM.

    Examples:
      anamne recap
      anamne recap --days 7      # recap the last week
      anamne recap --no-llm      # raw dump, no API call
    """
    import sqlite3
    from datetime import datetime, timezone, timedelta
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with sqlite3.connect(store._db) as con:
        # Facts created in period
        new_facts = con.execute(
            "SELECT id, fact, tags FROM scratchpad WHERE created_at >= ?",
            (cutoff,)
        ).fetchall()

        # Facts retrieved in period (from retrieval_log)
        retrieved_ids = con.execute(
            "SELECT DISTINCT fact_id FROM retrieval_log WHERE retrieved_at >= ?",
            (cutoff,)
        ).fetchall()
        retrieved_ids_set = {r[0] for r in retrieved_ids}

        # All those facts' content
        if retrieved_ids_set:
            placeholders = ",".join("?" * len(retrieved_ids_set))
            retrieved_facts = con.execute(
                f"SELECT id, fact, tags FROM scratchpad WHERE id IN ({placeholders})",
                list(retrieved_ids_set)
            ).fetchall()
        else:
            retrieved_facts = []

    import json as _json
    new_created = [
        {"id": r[0], "fact": r[1], "tags": _json.loads(r[2])} for r in new_facts
    ]
    retrieved = [
        {"id": r[0], "fact": r[1], "tags": _json.loads(r[2])} for r in retrieved_facts
        if r[0] not in {f["id"] for f in new_created}  # avoid duplication
    ]
    working = store.working_active()

    period_str = f"today ({today})" if days == 1 else f"the last {days} days"

    if no_llm:
        console.print(f"\n[bold]Memory activity for {period_str}[/bold]\n")
        if new_created:
            console.print(f"[green]New facts ({len(new_created)}):[/green]")
            for f in new_created:
                console.print(f"  [dim]{f['id']}[/dim]  {f['fact'][:80]}")
            console.print()
        if retrieved:
            console.print(f"[cyan]Accessed facts ({len(retrieved)}):[/cyan]")
            for f in retrieved:
                console.print(f"  [dim]{f['id']}[/dim]  {f['fact'][:80]}")
            console.print()
        if working:
            console.print(f"[yellow]Active working memory ({len(working)}):[/yellow]")
            for w in working:
                console.print(f"  {w['note'][:80]}")
            console.print()
        if not new_created and not retrieved and not working:
            console.print(f"[dim]No memory activity in {period_str}.[/dim]")
        return

    # Need LLM
    from anamne.config import get_settings
    cfg = get_settings()
    if not (cfg.anthropic_api_key or cfg.gemini_api_key):
        console.print("[red]No API key configured.[/red] "
                      "Use --no-llm for raw output, or run anamne init.")
        raise typer.Exit(1)

    if not new_created and not retrieved and not working:
        console.print(f"\n[dim]No memory activity in {period_str} to recap.[/dim]\n")
        return

    # Build prompt
    sections = []
    if new_created:
        lines = "\n".join(f"- [{f['id']}] {f['fact']}" for f in new_created[:30])
        sections.append(f"FACTS ADDED:\n{lines}")
    if retrieved:
        lines = "\n".join(f"- [{f['id']}] {f['fact']}" for f in retrieved[:20])
        sections.append(f"FACTS ACCESSED (read or surfaced):\n{lines}")
    if working:
        lines = "\n".join(f"- {w['note']}" for w in working[:10])
        sections.append(f"CURRENT WORKING MEMORY:\n{lines}")

    prompt = (
        f"You are summarising a person's memory system activity for {period_str}.\n\n"
        + "\n\n".join(sections)
        + "\n\nWrite a short, human-readable recap (3-6 sentences) covering: "
        "what the person worked on or decided, what new context they captured, "
        "and any active session focus. Be specific. Use the actual fact content."
    )

    from anamne.llm import LLMClient
    llm = LLMClient()
    console.print()
    console.print(Panel(
        f"[bold]Recap for {period_str}[/bold]\n\n"
        "[dim]Summarising {nc} new + {nr} accessed facts + {nw} working notes...[/dim]".format(
            nc=len(new_created), nr=len(retrieved), nw=len(working)
        ),
        border_style="cyan",
    ))
    console.print()
    result = llm.complete(prompt, max_tokens=400)
    console.print(result.text.strip())
    console.print()


@app.command()
def journal(
    entry: str = typer.Argument(..., help="What you want to record"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Extra tags (repeatable)"),
) -> None:
    """Log a timestamped journal entry to scratchpad memory.

    Quick capture for things you want to remember: what you worked on today,
    a decision you made, something you learned. Stored in scratchpad with a
    'journal' tag and today's date prepended automatically.

    Examples:
      anamne journal "Chose Postgres over SQLite because we need concurrent writes"
      anamne journal "Finally fixed the Stripe webhook double-fire  - idempotency key was wrong"
    """
    from datetime import date
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    today = date.today().isoformat()
    full_text = f"[{today}] {entry}"
    tags = list({"journal"} | set(tag))
    mem_id = store.remember(full_text, tags=tags)
    console.print(f"[green]Journaled[/green] [dim]({mem_id})[/dim]: {full_text}")


@app.command(name="import-chat")
def import_chat(
    file: Path = typer.Argument(..., help="Exported conversation file (JSON or plain text)"),
    source: str = typer.Option(
        "auto", "--source", "-s",
        help="Source format: auto | claude | chatgpt | text"
    ),
    limit: int = typer.Option(
        30, "--limit", "-n", help="Max facts to extract"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show extracted facts without storing"
    ),
) -> None:
    """Extract and store memorable facts from an exported AI conversation.

    Point at an exported JSON or text file from Claude, ChatGPT, or any AI
    tool. The LLM scans the conversation and extracts durable facts worth
    keeping: preferences, decisions, technical context.

    To export:
      Claude.ai  -> Settings > Export Data (conversations.json)
      ChatGPT    -> Settings > Export Data (conversations.json)
      Cursor     -> Export conversation from chat panel
      Plain text -> Paste any conversation text into a .txt file

    Examples:
      anamne import-chat ~/Downloads/conversations.json
      anamne import-chat session.txt --source text --dry-run
    """
    _require_api_key()

    file_path = file.resolve()
    if not file_path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(1)

    # Load and normalise the conversation text
    raw = file_path.read_text(encoding="utf-8", errors="ignore")

    if source == "text" or file_path.suffix == ".txt":
        conversation_text = raw[:12000]
    else:
        conversation_text = _parse_chat_json(raw, source=source)

    if not conversation_text.strip():
        console.print("[yellow]Could not extract any conversation text.[/yellow]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold]Scanning[/bold] [cyan]{file_path.name}[/cyan] "
        f"[dim]({len(conversation_text)} chars)[/dim]...\n"
    )

    from anamne.llm import LLMClient
    llm = LLMClient()

    import json as _json
    extract_prompt = (
        "You are reading an AI conversation transcript. Extract durable facts "
        "that are worth keeping long-term  - things that will still be useful "
        "weeks from now.\n\n"
        "Keep:\n"
        "- Personal preferences and constraints the user expressed\n"
        "- Technical decisions made during the conversation\n"
        "- Project context (what they're building, tech stack, goals)\n"
        "- Recurring problems or patterns\n"
        "- Things the user said they want to remember\n\n"
        "Skip:\n"
        "- Specific code snippets (unless they encode a lasting decision)\n"
        "- Debugging steps that are now resolved\n"
        "- Questions that were answered and fully resolved\n"
        "- AI assistant responses (only what the USER said/decided)\n\n"
        f"Conversation (truncated):\n{conversation_text[:10000]}\n\n"
        f"Return ONLY a JSON array of up to {limit} strings. "
        "Example: [\"I prefer TypeScript over JavaScript\", \"This project uses Postgres\"]\n"
        "JSON array:"
    )

    try:
        raw_response = llm.complete(extract_prompt, max_tokens=1024).text.strip()
        # Strip code fence if present
        if raw_response.startswith("```"):
            raw_response = raw_response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            if raw_response.startswith("json"):
                raw_response = raw_response[4:].strip()
        extracted: list[str] = _json.loads(raw_response)
        if not isinstance(extracted, list):
            raise ValueError("Expected JSON array")
    except Exception as e:
        console.print(f"[red]Extraction failed ({e}).[/red] Try --source text.")
        raise typer.Exit(1)

    if not extracted:
        console.print("[yellow]No durable facts found in this conversation.[/yellow]")
        return

    console.print(f"[bold]Found {len(extracted)} fact(s):[/bold]\n")
    for i, fact in enumerate(extracted, 1):
        console.print(f"  [cyan]{i:2}.[/cyan] {fact}")

    if dry_run:
        console.print(f"\n[yellow]Dry run  - nothing stored.[/yellow] Remove --dry-run to save.")
        return

    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    source_tag = f"imported-{source}" if source != "auto" else "imported"
    for fact in extracted:
        store.remember(fact.strip(), tags=[source_tag, "chat-import"])

    console.print(
        f"\n[green]Stored {len(extracted)} fact(s)[/green] "
        f"[dim](tagged: {source_tag}, chat-import)[/dim]"
    )


@app.command(name="import-web")
def import_web(
    url: str = typer.Argument(..., help="URL to fetch and distill facts from"),
    limit: int = typer.Option(15, "--limit", "-n", help="Max facts to extract per page"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show facts without storing"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Extra tag(s) to apply"),
    crawl: bool = typer.Option(
        False, "--crawl", help="Crawl the entire site (follow links within same domain)"
    ),
    max_pages: int = typer.Option(
        20, "--max-pages", help="Max pages to crawl when --crawl is set"
    ),
) -> None:
    """Scrape a web page and distill key facts into scratchpad memory.

    With --crawl: follows all links within the same domain and distils facts
    from every page visited (up to --max-pages).

    The domain name is auto-added as a tag so you can filter later.

    Examples:
      anamne import-web https://12factor.net
      anamne import-web https://docs.python.org/3/library/asyncio.html --limit 10
      anamne import-web https://docs.example.com --crawl --max-pages 30
      anamne import-web https://example.com/adr/001 --tag architecture --dry-run
    """
    _require_api_key()
    import httpx
    import json as _json
    from urllib.parse import urlparse as _urlparse, urljoin, urldefrag

    from anamne.llm import LLMClient
    from anamne.store.graph import DecisionStore

    llm = LLMClient()
    store = DecisionStore()

    parsed_start = _urlparse(url)
    domain = parsed_start.netloc.lstrip("www.")
    base_tags = list({domain, "web-import", *tag})

    # Existing facts for dedup (avoid storing identical facts twice during crawl)
    existing_facts: set[str] = {
        f["fact"].strip() for f in store.list_facts(limit=100_000)
    }

    def _fetch_html(u: str) -> str | None:
        try:
            r = httpx.get(
                u, follow_redirects=True, timeout=20,
                headers={"User-Agent": "anamne/0.8.0 (fact-distiller)"},
            )
            r.raise_for_status()
            return r.text
        except Exception as exc:
            console.print(f"  [dim]skip ({exc})[/dim]")
            return None

    def _extract_links(html: str, base_url: str) -> list[str]:
        """Return same-domain absolute links from an HTML page."""
        from html.parser import HTMLParser

        class _LinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links: list[str] = []

            def handle_starttag(self, t, attrs):
                if t == "a":
                    href = dict(attrs).get("href", "")
                    if href:
                        self.links.append(href)

        p = _LinkParser()
        p.feed(html)
        result = []
        base_netloc = _urlparse(base_url).netloc
        for href in p.links:
            href, _ = urldefrag(href)
            abs_url = urljoin(base_url, href)
            pabs = _urlparse(abs_url)
            if pabs.netloc == base_netloc and pabs.scheme in ("http", "https"):
                result.append(abs_url)
        return result

    def _distil_page(page_url: str, html: str) -> list[str]:
        text = _strip_html(html)
        if len(text) < 100:
            return []
        prompt = (
            "You are reading a web page. Extract durable facts worth keeping long-term.\n\n"
            "Keep: core concepts, design principles, technical decisions, best practices, "
            "important constraints or gotchas.\n"
            "Skip: navigation, ads, boilerplate, obvious/common-knowledge facts.\n\n"
            f"Page URL: {page_url}\n"
            f"Page text (truncated):\n{text[:10000]}\n\n"
            f"Return ONLY a JSON array of up to {limit} concise fact strings.\n"
            "JSON array:"
        )
        try:
            raw = llm.complete(prompt, max_tokens=1024).text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            result = _json.loads(raw)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    # ----- Single-page mode -----
    if not crawl:
        console.print(f"\n[bold]Fetching[/bold] [cyan]{url}[/cyan] ...\n")
        html = _fetch_html(url)
        if not html:
            console.print("[red]Fetch failed.[/red]")
            raise typer.Exit(1)
        page_text = _strip_html(html)
        if len(page_text) < 100:
            console.print("[yellow]Page has very little text content.[/yellow]")
            raise typer.Exit(1)
        console.print(
            f"[dim]Extracted {len(page_text):,} chars  - distilling up to {limit} facts...[/dim]\n"
        )
        extracted = _distil_page(url, html)
        if not extracted:
            console.print("[yellow]No durable facts found on this page.[/yellow]")
            return
        console.print(f"[bold]Found {len(extracted)} fact(s):[/bold]\n")
        for i, fact in enumerate(extracted, 1):
            console.print(f"  [cyan]{i:2}.[/cyan] {fact}")
        if dry_run:
            console.print(f"\n[yellow]Dry run  - nothing stored.[/yellow] Remove --dry-run to save.")
            return
        new_count = 0
        for fact in extracted:
            f = fact.strip()
            if f and f not in existing_facts:
                store.remember(f, tags=base_tags)
                existing_facts.add(f)
                new_count += 1
        console.print(
            f"\n[green]Stored {new_count} fact(s)[/green] "
            f"[dim](tagged: {', '.join(sorted(base_tags))})[/dim]"
        )
        return

    # ----- Crawl mode (BFS within same domain) -----
    console.print(
        f"\n[bold]Crawling[/bold] [cyan]{domain}[/cyan] "
        f"(up to {max_pages} pages) ...\n"
    )

    visited: set[str] = set()
    queue: list[str] = [url]
    all_facts: list[str] = []
    pages_done = 0

    while queue and pages_done < max_pages:
        current_url = queue.pop(0)
        # Normalise
        current_url, _ = urldefrag(current_url)
        if current_url in visited:
            continue
        visited.add(current_url)
        pages_done += 1

        console.print(f"  [{pages_done}/{max_pages}] [cyan]{current_url[:80]}[/cyan]")
        html = _fetch_html(current_url)
        if not html:
            continue

        # Extract facts from this page
        facts = _distil_page(current_url, html)
        new_on_page = [f.strip() for f in facts if f.strip() and f.strip() not in existing_facts]
        if new_on_page:
            console.print(f"         [dim]+{len(new_on_page)} fact(s)[/dim]")
        all_facts.extend(new_on_page)
        for f in new_on_page:
            existing_facts.add(f)

        # Enqueue child links (BFS)
        for link in _extract_links(html, current_url):
            if link not in visited and link not in queue:
                queue.append(link)

    console.print(
        f"\n[bold]Crawl complete:[/bold] {pages_done} page(s), "
        f"{len(all_facts)} new fact(s) found\n"
    )

    if not all_facts:
        console.print("[yellow]No new facts found.[/yellow]")
        return

    for i, fact in enumerate(all_facts, 1):
        console.print(f"  [cyan]{i:2}.[/cyan] {fact}")

    if dry_run:
        console.print(f"\n[yellow]Dry run  - nothing stored.[/yellow]")
        return

    for fact in all_facts:
        store.remember(fact, tags=base_tags)

    console.print(
        f"\n[green]Stored {len(all_facts)} fact(s)[/green] "
        f"[dim](tagged: {', '.join(sorted(base_tags))})[/dim]"
    )


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities, returning plain text."""
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav", "header", "footer", "aside"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav", "header", "footer", "aside"):
                self._skip = False
            if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "br", "tr"):
                self._parts.append("\n")

        def handle_data(self, data):
            if not self._skip:
                stripped = data.strip()
                if stripped:
                    self._parts.append(stripped + " ")

        def handle_entityref(self, name):
            pass  # stdlib handles entities via unescape

    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor._parts)
    # Collapse whitespace
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _parse_chat_json(raw: str, source: str) -> str:
    """Try to extract human-readable conversation text from a JSON export."""
    import json as _json

    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        # Not valid JSON  - treat as text
        return raw[:12000]

    lines: list[str] = []

    # ChatGPT export: list of conversations, each with 'mapping' dict
    if isinstance(data, list) and data and "mapping" in data[0]:
        for conv in data[:5]:  # first 5 conversations
            mapping = conv.get("mapping", {})
            for node in mapping.values():
                msg = node.get("message") or {}
                role = (msg.get("author") or {}).get("role", "")
                parts = (msg.get("content") or {}).get("parts", [])
                if role == "user" and parts:
                    text = " ".join(str(p) for p in parts if isinstance(p, str))
                    if text.strip():
                        lines.append(f"User: {text.strip()}")

    # Claude export: list of conversations with 'chat_messages'
    elif isinstance(data, list) and data and "chat_messages" in data[0]:
        for conv in data[:5]:
            for msg in conv.get("chat_messages", []):
                if msg.get("sender") == "human":
                    text = msg.get("text", "")
                    if text.strip():
                        lines.append(f"User: {text.strip()[:500]}")

    # Generic: look for 'messages' array (OpenAI-ish format)
    elif isinstance(data, dict) and "messages" in data:
        for msg in data["messages"]:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    lines.append(f"User: {content.strip()[:500]}")

    # Unknown structure  - just dump readable content
    else:
        return _json.dumps(data, indent=2)[:12000]

    return "\n".join(lines)[:12000]


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag (repeatable)"),
    pinned_only: bool = typer.Option(False, "--pinned", help="Only show pinned facts"),
    no_rank: bool = typer.Option(
        False, "--no-rank", help="Skip ACT-R ranking, use raw recency order"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of pretty text"
    ),
) -> None:
    """Search scratchpad facts directly  - no LLM, no API key required.

    Results are ranked by ACT-R activation (recency + frequency of use)
    so the most relevant facts surface first. Uses hybrid search (substring
    + semantic embeddings) by default. Use --no-rank for raw recency order.

    Examples:
      anamne search postgres
      anamne search "python preference" --limit 5
      anamne search auth --tag security
      anamne search deploy --pinned    # only pinned facts matching "deploy"
      anamne search auth --json        # pipe-friendly JSON
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if no_rank:
        results = store.search_facts(query, limit=limit * 3, tags=tag or None)
    else:
        # Get ranked results then apply tag filter
        results = store.search_facts_ranked(query, limit=limit * 3)
        if tag:
            tag_set = set(tag)
            results = [f for f in results if tag_set.intersection(f.get("tags", []))]

    if pinned_only:
        results = [f for f in results if f.get("pinned")]
    results = results[:limit]

    if as_json:
        console.print(json.dumps(results, indent=2, default=str))
        return

    if not results:
        console.print(f"[dim]No scratchpad facts matching '[bold]{query}[/bold]'.[/dim]")
        console.print(
            "Try [bold]anamne remember \"...\"[/bold] to add facts, "
            "or [bold]anamne ask \"...\"[/bold] to query episodic memory."
        )
        return

    console.print(f"\n[bold]{len(results)} result(s) for '[cyan]{query}[/cyan]':[/bold]\n")
    for f in results:
        tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f.get("tags") else ""
        pin_str = "  [green][pin][/green]" if f.get("pinned") else ""
        console.print(f"  [cyan]{f['id']}[/cyan]{pin_str}  {f['fact']}{tag_str}")
    console.print()


@app.command()
def export(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="File to write (default: print to stdout)"
    ),
    fmt: str = typer.Option(
        "json", "--format", "-f", help="Output format: json | markdown"
    ),
    no_episodic: bool = typer.Option(False, "--no-episodic", help="Skip episodic memory"),
    no_facts: bool = typer.Option(False, "--no-facts", help="Skip scratchpad facts"),
    no_working: bool = typer.Option(False, "--no-working", help="Skip working memory"),
    tag: list[str] = typer.Option(
        [], "--tag", "-t",
        help="Export only scratchpad facts with this tag (repeatable); skips episodic + working"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", metavar="YYYY-MM-DD",
        help="Only export items created on/after this date (incremental backup)"
    ),
) -> None:
    """Export all memories to JSON or Markdown for backup or migration.

    Examples:
      anamne export --output backup.json
      anamne export --format markdown --output memories.md
      anamne export --no-episodic --output facts-only.json
      anamne export --tag python --output python-facts.json
      anamne export --since 2026-05-01 --output delta.json
    """
    import json as _json
    from datetime import date
    from anamne.store.graph import DecisionStore

    store = DecisionStore()

    # --tag implies facts-only (skip episodic and working)
    if tag:
        no_episodic = True
        no_working = True

    def _after_since(items: list[dict], key: str) -> list[dict]:
        if not since:
            return items
        return [it for it in items if (it.get(key) or "") >= since]

    if fmt == "markdown":
        lines: list[str] = [
            f"# ANAMNE Memory Export",
            f"*Exported {date.today().isoformat()}*"
            + (f" *(since {since})*" if since else "") + "\n",
        ]

        if not no_facts:
            facts = store.list_facts(limit=10_000, tags=tag or None)
            facts = _after_since(facts, "created_at")
            tag_header = f" (tag: {', '.join(tag)})" if tag else ""
            lines.append(f"## Scratchpad Facts ({len(facts)}{tag_header})\n")
            for f in facts:
                tag_str = f" _{', '.join(f['tags'])}_" if f.get("tags") else ""
                pin_str = " [PINNED]" if f.get("pinned") else ""
                lines.append(f"- **{f['id']}**{pin_str}: {f['fact']}{tag_str}")
            lines.append("")

        if not no_working:
            working_items = store.working_active()
            working_items = _after_since(working_items, "created_at")
            lines.append(f"## Working Memory ({len(working_items)} active)\n")
            for w in working_items:
                lines.append(f"- {w['note']} *(expires {w['expires_at']})*")
            lines.append("")

        if not no_episodic:
            decisions = store.list_all_decisions(limit=10_000)
            if since:
                decisions = [
                    d for d in decisions
                    if d.created_at.isoformat() >= since
                ]
            lines.append(f"## Episodic Memory ({len(decisions)} decisions)\n")
            for d in decisions:
                lines.append(
                    f"### {d.content}\n"
                    f"**Why:** {d.why}  \n"
                    f"**Source:** {d.source_type} `{d.short_ref}` "
                    f"by {d.source_author} ({d.created_at.strftime('%Y-%m-%d')})  \n"
                    f"**Files:** {', '.join(d.file_paths[:4]) or 'unknown'}\n"
                )

        content = "\n".join(lines)

    else:  # json
        from anamne import __version__
        payload: dict = {"exported_at": date.today().isoformat(), "version": __version__}
        if since:
            payload["since"] = since

        if not no_facts:
            facts = store.list_facts(limit=10_000, tags=tag or None)
            payload["scratchpad_facts"] = _after_since(facts, "created_at")

        if not no_working:
            payload["working_memory"] = _after_since(store.working_active(), "created_at")

        if not no_episodic:
            decisions = store.list_all_decisions(limit=10_000)
            if since:
                decisions = [
                    d for d in decisions
                    if d.created_at.isoformat() >= since
                ]
            payload["episodic_decisions"] = [d.to_dict() for d in decisions]

        content = _json.dumps(payload, indent=2, default=str)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Exported[/green] to [bold]{output}[/bold]")
    else:
        console.print(content)


@app.command(name="import-memory")
def import_memory(
    file: Path = typer.Argument(..., help="ANAMNE JSON export file to import"),
    no_facts: bool = typer.Option(False, "--no-facts", help="Skip scratchpad facts"),
    no_working: bool = typer.Option(False, "--no-working", help="Skip working memory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without storing"),
    skip_dupes: bool = typer.Option(
        True, "--skip-dupes/--allow-dupes",
        help="Skip facts whose exact text already exists in scratchpad (default: skip)",
    ),
    ttl: int = typer.Option(
        60, "--ttl", help="TTL in minutes for imported working-memory notes"
    ),
) -> None:
    """Import facts from another ANAMNE JSON export (backup restore / team sharing).

    Reads the JSON produced by `anamne export` and re-inserts scratchpad facts
    and active working-memory notes into the current store.

    Episodic decisions are NOT imported  - they are repo-specific and should be
    re-indexed with `anamne index` instead.

    Examples:
      anamne import-memory backup.json
      anamne import-memory team-facts.json --dry-run
      anamne import-memory old-machine.json --no-working --allow-dupes
    """
    import json as _json

    file_path = file.resolve()
    if not file_path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(1)

    try:
        payload = _json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Could not parse JSON:[/red] {e}")
        raise typer.Exit(1)

    if not isinstance(payload, dict):
        console.print("[red]Invalid export file  - expected a JSON object.[/red]")
        raise typer.Exit(1)

    export_version = payload.get("version", "unknown")
    exported_at = payload.get("exported_at", "unknown")
    console.print(
        f"\n[bold]Import from[/bold] [cyan]{file_path.name}[/cyan]  "
        f"[dim](exported {exported_at}, anamne {export_version})[/dim]\n"
    )

    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    # ---- Scratchpad facts ----
    facts_imported = facts_skipped = 0
    if not no_facts:
        raw_facts = payload.get("scratchpad_facts", [])
        if not isinstance(raw_facts, list):
            raw_facts = []

        # Build existing-text set for dedup
        if skip_dupes:
            existing_texts = {f["fact"].strip() for f in store.list_facts(limit=100_000)}
        else:
            existing_texts = set()

        console.print(f"[bold]Scratchpad facts:[/bold] {len(raw_facts)} in file\n")
        for f in raw_facts:
            text = (f.get("fact") or "").strip()
            tags = f.get("tags") or []
            if not text:
                continue
            if skip_dupes and text in existing_texts:
                facts_skipped += 1
                console.print(f"  [dim]skip (duplicate):[/dim] {text[:60]}")
                continue
            console.print(f"  [green]+[/green] {text[:72]}{'...' if len(text) > 72 else ''}")
            if not dry_run:
                store.remember(text, tags=tags)
                existing_texts.add(text)
            facts_imported += 1

    # ---- Working memory ----
    working_imported = 0
    if not no_working:
        raw_working = payload.get("working_memory", [])
        if not isinstance(raw_working, list):
            raw_working = []
        if raw_working:
            console.print(f"\n[bold]Working memory:[/bold] {len(raw_working)} note(s)\n")
            for w in raw_working:
                note = (w.get("note") or "").strip()
                if not note:
                    continue
                console.print(f"  [green]+[/green] {note[:72]}{'...' if len(note) > 72 else ''}")
                if not dry_run:
                    store.working_add(note, ttl_minutes=ttl)
                working_imported += 1

    # ---- Summary ----
    if dry_run:
        console.print(
            f"\n[yellow]Dry run[/yellow]  - nothing stored. "
            f"Would import {facts_imported} fact(s), {working_imported} working note(s)."
        )
    else:
        parts = []
        if facts_imported:
            parts.append(f"{facts_imported} fact(s)")
        if facts_skipped:
            parts.append(f"{facts_skipped} duplicate(s) skipped")
        if working_imported:
            parts.append(f"{working_imported} working note(s)")
        console.print(
            f"\n[green]Imported:[/green] {', '.join(parts) or 'nothing new'}"
        )


@app.command(name="capture-clipboard")
def capture_clipboard(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show clipboard without storing"
    ),
    distill: bool = typer.Option(
        False, "--distill", "-d",
        help="Use LLM to extract structured facts from the clipboard text"
    ),
) -> None:
    """Read the clipboard and offer to save it as a scratchpad fact.

    Useful for quickly capturing something interesting you've copied  - a quote,
    a decision, a snippet of context  - without switching to another app.

    With --distill, the LLM extracts multiple atomic facts from longer text.

    Examples:
      anamne capture-clipboard
      anamne capture-clipboard --distill
      anamne capture-clipboard --dry-run
    """
    text = _read_clipboard()
    if not text:
        console.print("[yellow]Clipboard is empty or could not be read.[/yellow]")
        raise typer.Exit(1)

    text = text.strip()
    preview = text[:300] + ("..." if len(text) > 300 else "")
    console.print(f"\n[bold]Clipboard ({len(text)} chars):[/bold]\n{preview}\n")

    if dry_run:
        console.print("[yellow]Dry run  - nothing stored.[/yellow]")
        return

    if distill:
        _require_api_key()
        from anamne.store.graph import DecisionStore
        store = DecisionStore()
        from anamne.llm import LLMClient
        import json as _json
        llm = LLMClient()
        prompt = (
            "Extract durable, atomic facts from the text below. Each fact "
            "should be a single self-contained statement useful weeks from now.\n\n"
            f"Text:\n{text[:8000]}\n\n"
            'Return ONLY a JSON array of strings. Example: ["fact one", "fact two"]\n'
            "JSON array:"
        )
        try:
            raw = llm.complete(prompt, max_tokens=512).text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            extracted = _json.loads(raw)
            if not isinstance(extracted, list):
                raise ValueError("Expected list")
        except Exception as e:
            console.print(f"[yellow]Distill failed ({e}), storing as one fact.[/yellow]")
            extracted = [text]

        for f in extracted:
            mem_id = store.remember(f.strip(), tags=["clipboard"])
            console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]: {f}")
        console.print(f"\n[dim]Stored {len(extracted)} fact(s).[/dim]")

    else:
        if not typer.confirm("Remember this?", default=True):
            console.print("[dim]Cancelled.[/dim]")
            return
        from anamne.store.graph import DecisionStore
        store = DecisionStore()
        mem_id = store.remember(text[:2000], tags=["clipboard"])
        console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]")


def _read_clipboard() -> str:
    """Read text from the system clipboard. Returns empty string on failure."""
    # Try pyperclip first (cross-platform, optional dep)
    try:
        import pyperclip  # type: ignore
        return pyperclip.paste() or ""
    except ImportError:
        pass

    # Windows fallback via PowerShell
    import platform
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            pass

    # macOS fallback via pbpaste
    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=5
            )
            return result.stdout
        except Exception:
            pass

    # Linux fallback via xclip/xsel
    if platform.system() == "Linux":
        for cmd in [["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]:
            try:
                import subprocess
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass

    return ""


@app.command()
def working(
    note: Optional[str] = typer.Argument(None, help="Note to add (omit to list)"),
    ttl: int = typer.Option(60, "--ttl", help="Minutes until auto-expire"),
    clear: bool = typer.Option(False, "--clear", help="Clear all working memory"),
    extend: Optional[str] = typer.Option(
        None, "--extend",
        metavar="ID:MINUTES",
        help="Extend expiry of an existing note: --extend <id>:<extra_minutes>"
    ),
    pin_id: Optional[str] = typer.Option(
        None, "--pin", metavar="WORKING_ID",
        help="Promote a working note to scratchpad AND pin it in one step"
    ),
    to_fact_id: Optional[str] = typer.Option(
        None, "--to-fact", metavar="WORKING_ID",
        help="Promote a working note to scratchpad WITHOUT pinning"
    ),
    tag: list[str] = typer.Option(
        [], "--tag", "-t",
        help="Tags to attach when promoting via --pin or --to-fact"
    ),
) -> None:
    """Manage working memory (short-lived session context).

    Examples:
      anamne working "debugging the auth middleware"
      anamne working                          # list active notes
      anamne working --clear                  # wipe all
      anamne working --extend abc123:60       # add 60 more minutes to note abc123
      anamne working --pin abc123 --tag db    # promote + pin in one step
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if pin_id:
        new_id = store.promote_working(pin_id, tags=tag or None)
        if new_id is None:
            console.print(f"[red]No working memory note with id: {pin_id}[/red]")
            raise typer.Exit(code=1)
        store.pin_fact(new_id)
        console.print(
            f"\n  [green]Promoted + pinned[/green]  "
            f"[dim]{pin_id}[/dim] -> [cyan]{new_id}[/cyan]\n"
        )
        return

    if to_fact_id:
        new_id = store.promote_working(to_fact_id, tags=tag or None)
        if new_id is None:
            console.print(f"[red]No working memory note with id: {to_fact_id}[/red]")
            raise typer.Exit(code=1)
        console.print(
            f"\n  [green]Promoted to scratchpad[/green]  "
            f"[dim]{to_fact_id}[/dim] -> [cyan]{new_id}[/cyan]\n"
        )
        return

    if clear:
        n = store.working_clear()
        console.print(f"[green]Cleared[/green] {n} working memory items")
        return

    if extend:
        import sqlite3
        from datetime import datetime, timezone, timedelta
        try:
            note_id, extra = extend.split(":", 1)
            extra_min = int(extra)
        except ValueError:
            console.print("[red]--extend format: <id>:<minutes>  e.g. abc123:60[/red]")
            raise typer.Exit(1)
        with sqlite3.connect(store._db) as con:
            row = con.execute(
                "SELECT expires_at FROM working_memory WHERE id = ?", (note_id,)
            ).fetchone()
            if not row:
                console.print(f"[yellow]No working memory note with id: {note_id}[/yellow]")
                raise typer.Exit(1)
            try:
                old_exp = datetime.fromisoformat(row[0])
            except Exception:
                old_exp = datetime.now(timezone.utc)
            # Extend from whichever is later: old expiry or now
            base = max(old_exp, datetime.now(timezone.utc))
            new_exp = base + timedelta(minutes=extra_min)
            con.execute(
                "UPDATE working_memory SET expires_at = ? WHERE id = ?",
                (new_exp.isoformat(), note_id),
            )
        console.print(f"  [green]Extended[/green] {note_id} by {extra_min} min - "
                      f"now expires {new_exp.isoformat()[:19]}")
        return

    if note:
        mem_id = store.working_add(note, ttl_minutes=ttl)
        console.print(f"[green]Added[/green] [dim]({mem_id}, expires in {ttl}m)[/dim]: {note}")
        return

    items = store.working_active()
    if not items:
        console.print("[dim]Working memory is empty.[/dim]")
        return
    console.print(f"\n[bold]Working memory ({len(items)} items):[/bold]\n")
    for w in items:
        console.print(f"  [cyan]{w['id']}[/cyan]  {w['note']}")
        console.print(f"           [dim]expires: {w['expires_at']}[/dim]")


@app.command(name="search-working")
def search_working(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
) -> None:
    """Search active working-memory notes using semantic + substring matching.

    Searches only non-expired notes. Useful when you have many session notes
    and want to find a specific one quickly.

    Examples:
      anamne search-working "auth"
      anamne search-working "login bug" --limit 5
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    results = store.search_working(query, limit=limit)

    if not results:
        console.print(f"[dim]No working-memory notes matching '[bold]{query}[/bold]'.[/dim]")
        return

    console.print(f"\n[bold]Working memory  - {len(results)} match(es) for '{query}':[/bold]\n")
    for w in results:
        console.print(f"  [cyan]{w['id']}[/cyan]  {w['note']}")
        console.print(f"           [dim]expires: {w['expires_at']}[/dim]")
    console.print()


@app.command()
def clear(
    layer: str = typer.Argument(
        ...,
        help="Memory layer to clear: scratchpad | working | episodic | all"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clear an entire memory layer (irreversible).

    Layers:
      scratchpad   - all durable facts and their ACT-R retrieval history
      working      - all active working-memory notes
      episodic     - all indexed decisions and commit history
      all          - everything above

    Examples:
      anamne clear working               # wipe session notes
      anamne clear scratchpad --yes      # skip confirmation
    """
    valid = {"scratchpad", "working", "episodic", "all"}
    if layer not in valid:
        console.print(
            f"[red]Unknown layer: {layer}[/red]  - choose from: {', '.join(sorted(valid))}"
        )
        raise typer.Exit(1)

    if not yes:
        confirm_msg = f"Delete ALL {layer} memory? This cannot be undone."
        if not typer.confirm(confirm_msg, default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if layer in ("scratchpad", "all"):
        n = store.clear_scratchpad()
        console.print(f"[green]Cleared[/green] {n} scratchpad fact(s)")

    if layer in ("working", "all"):
        n = store.clear_working()
        console.print(f"[green]Cleared[/green] {n} working memory note(s)")

    if layer in ("episodic", "all"):
        n = store.clear_episodic()
        console.print(f"[green]Cleared[/green] {n} episodic decision(s)")


@app.command()
def reminder(
    message: str = typer.Argument(..., help="Reminder text to store in working memory"),
    in_minutes: Optional[int] = typer.Option(None, "--in", "-i", metavar="MINUTES",
                                             help="Pop reminder in N minutes from now"),
    at_time: Optional[str] = typer.Option(None, "--at", "-a", metavar="HH:MM",
                                          help="Pop reminder at HH:MM today (or tomorrow if time has passed)"),
) -> None:
    """Store a time-bound reminder in working memory.

    The note auto-expires and is removed from working memory after the given time,
    just like any other working-memory note.  MCP tools will stop returning it once
    it expires.

    If neither --in nor --at is provided, the reminder expires in 60 minutes.

    Examples:
      anamne reminder "review PR #42"               # expires in 60 min
      anamne reminder "check deploy logs" --in 15   # expires in 15 min
      anamne reminder "standup meeting" --at 09:30  # expires at 09:30
    """
    from datetime import datetime, timezone, timedelta
    from anamne.store.graph import DecisionStore

    now = datetime.now(timezone.utc)

    if at_time:
        # Parse HH:MM and compute TTL
        try:
            parts = at_time.strip().split(":")
            if len(parts) != 2:
                raise ValueError
            h, m = int(parts[0]), int(parts[1])
            local_now = datetime.now()  # local time for comparison
            target = local_now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= local_now:
                # Time already passed today - schedule for tomorrow
                target += timedelta(days=1)
            ttl = int((target - local_now).total_seconds() / 60)
            if ttl < 1:
                ttl = 1
        except (ValueError, AttributeError):
            console.print(f"[red]Invalid time format: '{at_time}' - use HH:MM (e.g. 09:30)[/red]")
            raise typer.Exit(1)
        at_str = target.strftime("%H:%M")
    elif in_minutes is not None:
        if in_minutes < 1:
            console.print("[red]--in must be at least 1 minute[/red]")
            raise typer.Exit(1)
        ttl = in_minutes
        at_str = None
    else:
        ttl = 60
        at_str = None

    store = DecisionStore()
    note_text = f"[reminder] {message}"
    note_id = store.working_add(note_text, ttl_minutes=ttl)

    expire_desc = f"at {at_str}" if at_str else f"in {ttl} min"
    console.print(f"\n  [green]Reminder set[/green]  (expires {expire_desc})")
    console.print(f"  [dim]{note_id}[/dim]  {message}\n")


@app.command(name="forget-tag")
def forget_tag(
    tag: str = typer.Argument(..., help="Tag whose facts should be deleted"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete all scratchpad facts that carry a specific tag.

    Useful for bulk-cleaning an import batch, removing a deprecated topic,
    or wiping all facts from a specific web import session.

    Examples:
      anamne forget-tag web-import             # preview then confirm
      anamne forget-tag python --yes           # skip confirmation
      anamne forget-tag docs.example.com       # wipe a domain import
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    facts = store.list_facts(limit=10_000, tags=[tag])

    if not facts:
        console.print(f"[dim]No facts with tag '[cyan]{tag}[/cyan]'. Nothing to delete.[/dim]")
        return

    console.print(f"\n  [yellow]Found {len(facts)} fact(s) with tag '[cyan]{tag}[/cyan]':[/yellow]\n")
    for f in facts[:10]:
        console.print(f"  [dim]{f['id']}[/dim]  {f['fact'][:80]}")
    if len(facts) > 10:
        console.print(f"  [dim]... and {len(facts) - 10} more[/dim]")
    console.print()

    if not yes:
        if not typer.confirm(f"Delete all {len(facts)} fact(s) tagged '{tag}'?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    deleted = 0
    for f in facts:
        try:
            store.forget_fact(f["id"])
            deleted += 1
        except Exception:
            pass

    console.print(f"\n  [green]Deleted {deleted} fact(s) with tag '[cyan]{tag}[/cyan]'.[/green]\n")


@app.command()
def timeline(
    days: int = typer.Option(14, "--days", "-d", help="Days of history to show"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter facts by tag"),
) -> None:
    """Chronological view of memory activity, grouped by date.

    Shows for each day: facts created, facts retrieved (from retrieval_log),
    and any history events (edits, tag changes, deletions). Great for
    answering 'what happened on Tuesday?' or 'what have I been working on?'.

    Examples:
      anamne timeline
      anamne timeline --days 7
      anamne timeline --tag python --days 30
    """
    import sqlite3
    from collections import defaultdict
    from datetime import datetime, timezone, timedelta
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    db = store.data_dir / "anamne.db"
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    by_day: dict[str, dict] = defaultdict(lambda: {"created": [], "retrieved": 0, "events": 0})

    with sqlite3.connect(db) as con:
        # Created facts
        rows = con.execute(
            "SELECT id, fact, tags, created_at FROM scratchpad "
            "WHERE created_at >= ? ORDER BY created_at ASC",
            (cutoff,),
        ).fetchall()
        tag_set = set(tag)
        for fid, fact, tags_json, created_at in rows:
            tags = json.loads(tags_json) if tags_json else []
            if tag_set and not tag_set.intersection(tags):
                continue
            day = created_at[:10]
            by_day[day]["created"].append((fid, fact[:60]))

        # Retrievals (no tag filter applied — already approximate)
        try:
            retr_rows = con.execute(
                "SELECT DATE(retrieved_at), COUNT(*) FROM retrieval_log "
                "WHERE retrieved_at >= ? GROUP BY DATE(retrieved_at)",
                (cutoff,),
            ).fetchall()
            for day, cnt in retr_rows:
                by_day[day]["retrieved"] = cnt
        except Exception:
            pass

        # History events
        try:
            evt_rows = con.execute(
                "SELECT DATE(changed_at), COUNT(*) FROM fact_history "
                "WHERE changed_at >= ? GROUP BY DATE(changed_at)",
                (cutoff,),
            ).fetchall()
            for day, cnt in evt_rows:
                by_day[day]["events"] = cnt
        except Exception:
            pass

    if not by_day:
        console.print(f"\n  [dim]No memory activity in the last {days} day(s).[/dim]\n")
        return

    console.print(f"\n  [bold]Memory timeline - last {days} day(s)[/bold]\n")
    for day in sorted(by_day.keys()):
        info = by_day[day]
        n_created = len(info["created"])
        parts: list[str] = []
        if n_created:
            parts.append(f"[green]{n_created} created[/green]")
        if info["retrieved"]:
            parts.append(f"[cyan]{info['retrieved']} retrieved[/cyan]")
        if info["events"]:
            parts.append(f"[yellow]{info['events']} events[/yellow]")
        summary = ", ".join(parts) if parts else "[dim]quiet[/dim]"
        console.print(f"  [bold]{day}[/bold]  {summary}")
        for fid, snippet in info["created"][:3]:
            console.print(f"    [dim]+ {fid}[/dim]  {snippet}")
        if n_created > 3:
            console.print(f"    [dim]  ...and {n_created - 3} more[/dim]")
    console.print()


@app.command()
def tags(
    sort: str = typer.Option("count", "--sort", "-s", help="Sort: count | name"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max tags to display"),
) -> None:
    """List every distinct tag with its fact count.

    A lighter alternative to `anamne tag-stats` when you just need to scan
    what tags exist.

    Examples:
      anamne tags
      anamne tags --sort name
      anamne tags --limit 200
    """
    from collections import Counter
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    all_facts = store.list_facts(limit=10_000)
    counter: Counter = Counter()
    for f in all_facts:
        for t in (f.get("tags") or []):
            counter[t] += 1

    if not counter:
        console.print("\n  [dim]No tags found.[/dim]\n")
        return

    if sort == "name":
        items = sorted(counter.items())
    else:
        items = counter.most_common()
    items = items[:limit]

    console.print(f"\n  [bold]{len(counter)} distinct tag(s)[/bold] "
                  f"(showing {len(items)}):\n")
    for name, cnt in items:
        console.print(f"  [cyan]{name:30}[/cyan] [dim]{cnt}[/dim]")
    console.print()


@app.command(name="suggest-pins")
def suggest_pins(
    candidates: int = typer.Option(20, "--candidates", "-n",
                                   help="How many top-activation facts to consider"),
    apply: bool = typer.Option(False, "--apply", help="Pin the suggestions automatically"),
) -> None:
    """Ask the LLM which of your most-accessed facts deserve to be pinned.

    Workflow:
      1. Pulls the top-N unpinned facts by ACT-R activation.
      2. Asks the LLM to pick the ones that look like durable preferences,
         architecture decisions, or constraints (vs. transient context).
      3. Prints the suggested ids. With --apply, pins them in place.

    Falls back to the top-activation list verbatim when no API key is set.

    Examples:
      anamne suggest-pins
      anamne suggest-pins --candidates 30
      anamne suggest-pins --apply
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    all_facts = store.list_facts(limit=10_000)
    unpinned = [f for f in all_facts if not f.get("pinned")]
    if not unpinned:
        console.print("\n  [dim]Every fact is already pinned (or scratchpad is empty).[/dim]\n")
        return

    scored = sorted(
        ((store.activation_score(f["id"]), f) for f in unpinned),
        key=lambda x: x[0], reverse=True,
    )
    pool = [f for _, f in scored[:candidates]]

    fact_lines = "\n".join(
        f"- {f['id']}: {f['fact']} (tags: {', '.join(f['tags']) or 'none'})"
        for f in pool
    )

    suggested_ids: list[str] = []
    try:
        from anamne.llm import LLMClient
        client = LLMClient()
        prompt = (
            "Below are scratchpad facts the user accesses often. Which of them "
            "look like DURABLE personal preferences, architecture decisions, or "
            "long-lived constraints worth protecting from auto-consolidation? "
            "Skip transient notes, journal-style entries, and one-off tasks.\n\n"
            "Reply with a comma-separated list of fact ids ONLY (no prose, no "
            "bullets). If none qualify, reply with NONE.\n\n"
            f"FACTS:\n{fact_lines}\n\nIDS:"
        )
        raw = client.complete(prompt, max_tokens=200).text.strip()
        if raw.upper() != "NONE":
            for tok in raw.replace(",", " ").split():
                tok = tok.strip().strip(",.;:")
                if tok and tok != "NONE" and any(p["id"] == tok for p in pool):
                    suggested_ids.append(tok)
    except Exception as e:
        console.print(f"  [yellow]LLM unavailable ({e}); falling back to top "
                      "activation.[/yellow]\n")
        suggested_ids = [f["id"] for f in pool[:5]]

    if not suggested_ids:
        console.print("\n  [dim]No pin suggestions from the LLM.[/dim]\n")
        return

    console.print(f"\n  [bold]Suggested pins ({len(suggested_ids)}):[/bold]\n")
    for fid in suggested_ids:
        match = next((p for p in pool if p["id"] == fid), None)
        if match:
            tags = ", ".join(match["tags"]) if match["tags"] else "-"
            console.print(f"  [cyan]{fid}[/cyan]  {match['fact']}")
            console.print(f"      [dim]tags:[/dim] {tags}")
    console.print()

    if apply:
        applied = 0
        for fid in suggested_ids:
            try:
                if store.pin_fact(fid):
                    applied += 1
            except Exception:
                pass
        console.print(f"  [green]Pinned {applied} fact(s).[/green]\n")
    else:
        console.print("  [dim]Run again with [bold]--apply[/bold] to pin these.[/dim]\n")


@app.command()
def similar(
    text: str = typer.Argument(..., help="Free-text query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter results by tag"),
) -> None:
    """Pure-semantic search over scratchpad facts (no substring, no ACT-R rerank).

    Differs from `anamne search`:
      - `search` is hybrid (substring + semantic + ACT-R activation rerank)
      - `similar` is pure ChromaDB nearest-neighbor on embeddings

    Useful when you don't know the exact terminology and want conceptual matches.

    Examples:
      anamne similar "why we picked our database"
      anamne similar "deployment philosophy" --limit 5
      anamne similar "design choices" --tag architecture
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    fetch_limit = limit * 3 if tag else limit
    results = store.search_facts_semantic(text, limit=fetch_limit)
    if tag:
        tag_set = set(tag)
        results = [r for r in results if tag_set.intersection(r.get("tags", []))]
    results = results[:limit]
    if not results:
        console.print(f"\n  [dim]No semantically similar facts found for "
                      f"'[cyan]{text}[/cyan]'.[/dim]\n")
        return
    console.print(f"\n  [bold]{len(results)} similar fact(s) for "
                  f"'[cyan]{text}[/cyan]':[/bold]\n")
    for f in results:
        tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f.get("tags") else ""
        console.print(f"  [cyan]{f['id']}[/cyan]  {f['fact']}{tag_str}")
    console.print()


@app.command(name="suggest-tags")
def suggest_tags_cmd(
    text: str = typer.Argument(..., help="Free-text content to suggest tags for"),
    max_tags: int = typer.Option(5, "--max", "-n", help="Max tag suggestions"),
) -> None:
    """Preview LLM-suggested tags for arbitrary text without storing anything.

    Useful to check what `remember --auto-tag` would pick, or to brainstorm
    tag candidates for an upcoming batch import.

    Examples:
      anamne suggest-tags "Switched from MySQL to Postgres for concurrency"
      anamne suggest-tags "Stripe webhook idempotency key was wrong" --max 3
    """
    from anamne.store.graph import DecisionStore
    from anamne.llm import LLMClient

    store = DecisionStore()
    existing_tags = sorted({
        t for f in store.list_facts(limit=10_000) for t in (f.get("tags") or [])
    })
    existing_blurb = (
        f"Existing tags in this user's memory: {', '.join(existing_tags[:60])}.\n\n"
        if existing_tags else ""
    )

    try:
        client = LLMClient()
        prompt = (
            "Suggest up to "
            f"{max_tags} short tag labels (lowercase, hyphen-separated, no spaces) "
            "for the following user fact. Prefer reusing existing tags when they "
            "fit; introduce new ones only when needed.\n\n"
            f"{existing_blurb}"
            f"FACT:\n{text}\n\n"
            "Return ONLY a comma-separated tag list, no prose."
        )
        raw = client.complete(prompt, max_tokens=120).text.strip()
        tags = [t.strip().strip(",.;:") for t in raw.replace("\n", ",").split(",")]
        tags = [t for t in tags if t and " " not in t][:max_tags]
    except Exception as e:
        console.print(f"\n  [yellow]LLM unavailable ({e}).[/yellow]\n")
        raise typer.Exit(code=1)

    if not tags:
        console.print("\n  [dim]No tags suggested.[/dim]\n")
        return
    console.print(f"\n  [bold]Suggested tags:[/bold]  {', '.join(tags)}\n")
    console.print("  [dim]Use them with:[/dim]")
    flags = " ".join(f"--tag {t}" for t in tags)
    console.print(f"  anamne remember \"{text[:60]}...\" {flags}\n")


@app.command()
def promote(
    working_id: str = typer.Argument(..., help="Working memory note id to promote"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tag for the new fact"),
) -> None:
    """Promote a working-memory note into a permanent scratchpad fact.

    The note is removed from working memory and stored as a regular fact.
    Useful workflow: jot transient context with `anamne working "..."`,
    then promote what turns out to matter.

    Examples:
      anamne promote abc123
      anamne promote abc123 --tag architecture --tag postgres
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    new_id = store.promote_working(working_id, tags=tag or None)
    if new_id is None:
        console.print(f"[red]No working memory note with id '{working_id}'.[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"\n  [green]Promoted[/green] working note "
        f"[dim]{working_id}[/dim] -> scratchpad fact "
        f"[cyan]{new_id}[/cyan]\n"
    )


@app.command()
def profile() -> None:
    """LLM-generated 'about me' summary from your scratchpad facts.

    Pulls every pinned and frequently-accessed fact and asks the LLM to write
    a concise multi-paragraph profile. Helpful for sharing context with a new
    AI assistant or refreshing your own view of long-term preferences.

    Skips the LLM step if no API key is configured (raw fact dump instead).

    Examples:
      anamne profile
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    all_facts = store.list_facts(limit=10_000)
    if not all_facts:
        console.print("\n  [dim]No facts to profile yet.[/dim]\n")
        return

    # Prefer pinned facts; supplement with top-activation
    pinned = [f for f in all_facts if f.get("pinned")]
    scored = sorted(
        ((store.activation_score(f["id"]), f) for f in all_facts if not f.get("pinned")),
        key=lambda x: x[0], reverse=True,
    )
    top_activation = [f for _, f in scored[:20]]
    profile_facts = pinned + top_activation
    # Dedupe by id while preserving order
    seen: set[str] = set()
    profile_facts = [
        f for f in profile_facts if not (f["id"] in seen or seen.add(f["id"]))
    ][:30]

    fact_lines = "\n".join(
        f"- {f['fact']} (tags: {', '.join(f['tags']) or 'none'})"
        for f in profile_facts
    )

    try:
        from anamne.llm import LLMClient
        client = LLMClient()
        prompt = (
            "Below are the most-important persistent facts the user has saved "
            "about themselves, their preferences, and their projects.\n\n"
            "Write a concise multi-paragraph 'profile' summarising who this user "
            "is, what they care about, and how they work. Use only the facts "
            "below; do not invent details. 3-5 short paragraphs.\n\n"
            f"FACTS:\n{fact_lines}\n\nPROFILE:"
        )
        result = client.complete(prompt, max_tokens=900).text.strip()
        console.print("\n  [bold]Profile[/bold]  "
                      f"[dim](from {len(profile_facts)} facts)[/dim]\n")
        console.print(result)
        console.print()
    except Exception as e:
        console.print(
            f"\n  [yellow]LLM unavailable ({e}). Showing raw facts.[/yellow]\n"
        )
        for f in profile_facts:
            console.print(f"  [dim]{f['id']}[/dim]  {f['fact']}")
        console.print()


@app.command()
def related(
    memory_id: str = typer.Argument(..., help="Memory ID to find related facts for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max number of related facts"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter neighbors by tag"),
) -> None:
    """Find scratchpad facts most semantically similar to a given fact.

    Uses ChromaDB embeddings to find neighbors. Useful for discovering hidden
    clusters and duplicates that exact-text dedupe would miss.

    Examples:
      anamne related abc123
      anamne related abc123 --limit 5
      anamne related abc123 --tag python   # only neighbors with the 'python' tag
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    source = store.get_fact(memory_id)
    if source is None:
        console.print(f"[red]No fact found with id '{memory_id}'.[/red]")
        raise typer.Exit(code=1)

    # Over-fetch when tag-filtering so we still hit `limit` after filter
    fetch_limit = limit * 3 if tag else limit
    results = store.related_facts(memory_id, limit=fetch_limit)
    if tag:
        tag_set = set(tag)
        results = [r for r in results if tag_set.intersection(r.get("tags", []))]
    results = results[:limit]
    console.print()
    console.print(f"  [dim]Source:[/dim] [cyan]{source['fact']}[/cyan]")
    console.print()
    if not results:
        console.print("  [dim]No related facts found.[/dim]\n")
        return

    console.print(f"  [bold]Top {len(results)} related fact(s):[/bold]\n")
    for f in results:
        pin = " [yellow]*[/yellow]" if f.get("pinned") else ""
        tags = ", ".join(f["tags"]) if f["tags"] else "-"
        console.print(f"  [dim]{f['id']}[/dim]{pin}  {f['fact'][:80]}")
        console.print(f"      [dim]tags:[/dim] {tags}")
    console.print()
    # Touch the source so frequent "related" lookups boost its activation
    try:
        store.touch_facts([memory_id])
    except Exception:
        pass


@app.command(name="tag-rename")
def tag_rename(
    old: str = typer.Argument(..., help="Existing tag to rename"),
    new: str = typer.Argument(..., help="New tag name"),
) -> None:
    """Rename a tag across every scratchpad fact in one step.

    If a fact already carries the new tag, the old tag is just dropped.
    A history row is recorded for every modified fact.

    Examples:
      anamne tag-rename pyhton python
      anamne tag-rename backend services
    """
    from anamne.store.graph import DecisionStore

    if not old.strip() or not new.strip():
        console.print("[red]Both old and new tag names are required.[/red]")
        raise typer.Exit(code=1)
    if old == new:
        console.print("[yellow]Old and new tag are identical. Nothing to do.[/yellow]")
        return

    store = DecisionStore()
    affected = store.rename_tag(old.strip(), new.strip())
    if affected == 0:
        console.print(f"\n  [dim]No facts had tag '[cyan]{old}[/cyan]'. Nothing changed.[/dim]\n")
        return
    console.print(
        f"\n  [green]Renamed tag '[cyan]{old}[/cyan]' -> "
        f"'[cyan]{new}[/cyan]' on {affected} fact(s).[/green]\n"
    )


@app.command(name="tag-clear")
def tag_clear(
    tag: str = typer.Argument(..., help="Tag to remove from all facts"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a tag from every fact that has it, keeping the facts intact.

    Unlike `forget-tag` (which deletes the facts themselves), this command
    only strips the tag and preserves all fact content.

    Examples:
      anamne tag-clear deprecated
      anamne tag-clear web-import --yes
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    facts = store.list_facts(limit=10_000, tags=[tag])
    if not facts:
        console.print(f"\n  [dim]No facts have tag '[cyan]{tag}[/cyan]'.[/dim]\n")
        return

    if not yes:
        console.print(
            f"\n  [yellow]About to strip tag '[cyan]{tag}[/cyan]' "
            f"from {len(facts)} fact(s) (facts will be kept).[/yellow]\n"
        )
        if not typer.confirm("Proceed?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    affected = store.remove_tag_from_all(tag)
    console.print(
        f"\n  [green]Removed tag '[cyan]{tag}[/cyan]' from {affected} fact(s).[/green]\n"
    )


@app.command()
def doctor() -> None:
    """Diagnose common ANAMNE problems and report the health of your installation.

    Checks:
      • API key configuration (Anthropic / Gemini)
      • Data directory and SQLite accessibility
      • ChromaDB collections and scratchpad sync status
      • Memory layer counts
      • Version info

    Run this first when something isn't working as expected.
    """
    import sys
    from pathlib import Path as _Path
    from rich.table import Table

    ok_mark   = "[green]OK [/green]"
    warn_mark = "[yellow]!! [/yellow]"
    fail_mark = "[red]ERR[/red]"

    issues: list[str] = []

    console.print()
    console.print("[bold]ANAMNE Doctor[/bold]   -  installation health check\n")

    # ── Version ──────────────────────────────────────────────────────────── #
    from anamne import __version__
    console.print(f"  {ok_mark}  anamne version   : [cyan]{__version__}[/cyan]")
    console.print(f"  {ok_mark}  python           : {sys.version.split()[0]}")

    # ── Config & API keys ─────────────────────────────────────────────────── #
    try:
        from anamne.config import get_settings
        cfg = get_settings()
        data_dir = cfg.data_dir
        console.print(f"  {ok_mark}  data directory   : {data_dir}")
    except Exception as e:
        console.print(f"  {fail_mark}  config error     : {e}")
        issues.append(f"config: {e}")
        data_dir = _Path.home() / ".anamne"

    has_anthropic = bool(getattr(cfg, "anthropic_api_key", None))
    has_gemini    = bool(getattr(cfg, "gemini_api_key", None))

    if has_anthropic:
        console.print(f"  {ok_mark}  ANTHROPIC_API_KEY: set")
    else:
        console.print(f"  {warn_mark}  ANTHROPIC_API_KEY: [yellow]not set[/yellow]")

    if has_gemini:
        console.print(f"  {ok_mark}  GEMINI_API_KEY   : set")
    else:
        console.print(f"  {warn_mark}  GEMINI_API_KEY   : [yellow]not set[/yellow]")

    if not has_anthropic and not has_gemini:
        issues.append("No LLM API key set  - run `anamne init` or set ANTHROPIC_API_KEY / GEMINI_API_KEY in .env")
        console.print(f"        [red]No API key configured. LLM commands will fail.[/red]")

    # ── Data directory ────────────────────────────────────────────────────── #
    if data_dir.exists():
        console.print(f"  {ok_mark}  data dir exists  : yes")
    else:
        console.print(f"  {warn_mark}  data dir exists  : [yellow]no (will be created on first use)[/yellow]")

    # ── SQLite ────────────────────────────────────────────────────────────── #
    try:
        from anamne.store.graph import DecisionStore
        store = DecisionStore()
        facts     = store.fact_count()
        decisions = store.count()
        working   = len(store.working_active())
        console.print(f"  {ok_mark}  SQLite           : accessible")
        console.print(f"  {ok_mark}  scratchpad facts : {facts}")
        console.print(f"  {ok_mark}  episodic records : {decisions}")
        console.print(f"  {ok_mark}  working memory   : {working} active")
    except Exception as e:
        console.print(f"  {fail_mark}  SQLite error     : [red]{e}[/red]")
        issues.append(f"SQLite: {e}")
        store = None

    # ── ChromaDB ──────────────────────────────────────────────────────────── #
    if store is not None:
        try:
            chroma_facts    = store._scratch_col.count()
            chroma_episodes = store._col.count()
            chroma_working  = store._working_col.count()

            # Scratchpad sync check
            if chroma_facts < facts:
                lag = facts - chroma_facts
                console.print(
                    f"  {warn_mark}  ChromaDB scratchpad: {chroma_facts} "
                    f"[yellow](SQLite has {facts}  - {lag} not yet embedded)[/yellow]"
                )
                issues.append(
                    f"ChromaDB scratchpad is {lag} fact(s) behind SQLite. "
                    "This is auto-fixed on the next startup."
                )
            else:
                console.print(f"  {ok_mark}  ChromaDB scratchpad: {chroma_facts} (in sync)")

            console.print(f"  {ok_mark}  ChromaDB episodic  : {chroma_episodes}")
            console.print(f"  {ok_mark}  ChromaDB working   : {chroma_working}")
        except Exception as e:
            console.print(f"  {fail_mark}  ChromaDB error   : [red]{e}[/red]")
            issues.append(f"ChromaDB: {e}")

    # ── Model ─────────────────────────────────────────────────────────────── #
    if store is not None:
        try:
            model = cfg.resolved_model()
            console.print(f"  {ok_mark}  active model     : [cyan]{model}[/cyan]")
        except Exception:
            console.print(f"  {warn_mark}  active model     : [yellow]could not resolve[/yellow]")

    # ── Summary ───────────────────────────────────────────────────────────── #
    console.print()
    if issues:
        console.print(f"[yellow]Found {len(issues)} issue(s):[/yellow]\n")
        for i, issue in enumerate(issues, 1):
            console.print(f"  [yellow]{i}.[/yellow] {issue}")
        console.print()
    else:
        console.print("[green]Everything looks healthy![/green]  "
                      "Run [bold]anamne status[/bold] for memory stats.\n")


@app.command()
def status() -> None:
    """Show knowledge base stats."""
    from anamne.config import get_settings
    from anamne.store.graph import DecisionStore

    cfg = get_settings()
    store = DecisionStore()
    count = store.count()
    repos = store.all_repos()

    table = Table(
        title="anamne Status",
        border_style="green",
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value")

    fact_count = store.fact_count()
    work_count = len(store.working_active())

    scratch_in_chroma = store._scratch_col.count()
    table.add_row("Episodic memory", f"[bold]{count}[/bold] decisions")
    table.add_row(
        "Scratchpad facts",
        f"[bold]{fact_count}[/bold] facts  "
        f"[dim]({scratch_in_chroma} embedded for semantic search)[/dim]",
    )
    table.add_row("Working memory", f"[bold]{work_count}[/bold] active notes")
    table.add_row(
        "Status",
        "[green]ready[/green]" if (count + fact_count) > 0
        else "[yellow]empty  - run: anamne index . or anamne remember ...[/yellow]",
    )
    table.add_row("Indexed repos", str(len(repos)) if repos else "none")
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Model", cfg.resolved_model() or "[dim](not set)[/dim]")
    table.add_row("Provider", cfg.model_tier())
    table.add_row(
        "API key",
        "[green]set[/green]"
        if (cfg.anthropic_api_key and cfg.anthropic_api_key != "your-key-here")
           or cfg.gemini_api_key
        else "[red]missing[/red]",
    )

    if repos:
        table.add_row("Repos", "\n".join(repos))

    # Top-tags breakdown
    if fact_count > 0:
        from collections import Counter
        all_facts = store.list_facts(limit=10_000)
        tag_counter: Counter = Counter()
        untagged = 0
        for f in all_facts:
            if f.get("tags"):
                tag_counter.update(f["tags"])
            else:
                untagged += 1
        if tag_counter:
            top = tag_counter.most_common(8)
            tag_summary = "  ".join(f"[cyan]{t}[/cyan]:{n}" for t, n in top)
            if untagged:
                tag_summary += f"  [dim](+{untagged} untagged)[/dim]"
            table.add_row("Top tags", tag_summary)

    console.print()
    console.print(table)
    console.print()


@app.command()
def stats(
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of pretty tables"
    ),
) -> None:
    """Detailed memory statistics - most accessed facts, creation rate, ACT-R summary.

    Complements `anamne status` with deeper analytics:
      - Most retrieved facts (by retrieval_log count)
      - Facts added per day over the last 14 days
      - Oldest and newest scratchpad facts
      - Average ACT-R activation across all facts

    Examples:
      anamne stats
      anamne stats --json     # for scripts / dashboards
    """
    import math
    import sqlite3
    from datetime import datetime, timezone
    from collections import Counter
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    db = store._db

    fact_count = store.fact_count()
    decision_count = store.count()
    working_count = len(store.working_active())

    if as_json:
        # Compact analytics payload, skipping the expensive ACT-R loop
        # over very large stores. Pretty output below still does it.
        with sqlite3.connect(db) as con:
            top_retrieved_rows = con.execute("""
                SELECT r.fact_id, COUNT(*) as hits, s.fact
                FROM retrieval_log r
                LEFT JOIN scratchpad s ON s.id = r.fact_id
                GROUP BY r.fact_id
                ORDER BY hits DESC
                LIMIT 5
            """).fetchall()
            total_retr = con.execute(
                "SELECT COUNT(*) FROM retrieval_log"
            ).fetchone()[0]
            creation_rows = con.execute("""
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM scratchpad
                WHERE created_at >= DATE('now', '-14 days')
                GROUP BY day ORDER BY day ASC
            """).fetchall()
        tag_counter: Counter = Counter()
        for f in store.list_facts(limit=10_000):
            for t in (f.get("tags") or []):
                tag_counter[t] += 1
        payload = {
            "scratchpad_facts": fact_count,
            "episodic_decisions": decision_count,
            "working_active": working_count,
            "total_retrievals": total_retr,
            "top_retrieved": [
                {"id": fid, "hits": hits, "fact": (fact_text or "")[:80]}
                for (fid, hits, fact_text) in top_retrieved_rows
            ],
            "creation_per_day": {day: cnt for day, cnt in creation_rows},
            "top_tags": dict(tag_counter.most_common(15)),
        }
        console.print(json.dumps(payload, indent=2, default=str))
        return

    console.print()
    console.print("[bold cyan]ANAMNE -- Memory Statistics[/bold cyan]")
    console.print()

    # ---- Layer summary ----
    layer_table = Table(border_style="cyan", show_header=False, padding=(0, 2))
    layer_table.add_column("Layer", style="cyan")
    layer_table.add_column("Count")
    layer_table.add_row("Scratchpad facts", f"[bold]{fact_count}[/bold]")
    layer_table.add_row("Episodic decisions", f"[bold]{decision_count}[/bold]")
    layer_table.add_row("Working notes (active)", f"[bold]{working_count}[/bold]")
    console.print(layer_table)
    console.print()

    if fact_count == 0:
        console.print("[dim]No scratchpad facts yet. Run: anamne remember ...[/dim]")
        console.print()
        return

    with sqlite3.connect(db) as con:
        # ---- Most retrieved facts ----
        top_retrieved = con.execute("""
            SELECT r.fact_id, COUNT(*) as hits, s.fact
            FROM retrieval_log r
            LEFT JOIN scratchpad s ON s.id = r.fact_id
            GROUP BY r.fact_id
            ORDER BY hits DESC
            LIMIT 5
        """).fetchall()

        # ---- Total retrievals ----
        total_retrievals = con.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0]

        # ---- ACT-R stats ----
        all_fact_ids = con.execute("SELECT id FROM scratchpad").fetchall()

        # ---- Creation rate - last 14 days ----
        creation_rows = con.execute("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM scratchpad
            WHERE created_at >= DATE('now', '-14 days')
            GROUP BY day
            ORDER BY day ASC
        """).fetchall()

        # ---- Oldest and newest ----
        oldest = con.execute(
            "SELECT id, fact, created_at FROM scratchpad ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        newest = con.execute(
            "SELECT id, fact, created_at FROM scratchpad ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        # ---- Tag stats ----
        tag_rows = con.execute("SELECT tags FROM scratchpad WHERE tags IS NOT NULL AND tags != ''").fetchall()

    # ---- ACT-R average ----
    now = datetime.now(timezone.utc)
    decay = 0.5
    activations = []
    for (fid,) in all_fact_ids:
        score = store.activation_score(fid, decay)
        if score > 0:
            activations.append(score)
    avg_activation = sum(activations) / len(activations) if activations else 0.0
    facts_with_retrievals = len(activations)

    # ---- Print most retrieved ----
    if top_retrieved:
        console.print("[bold]Most accessed facts[/bold]  (by retrieval count):")
        top_table = Table(border_style="dim", padding=(0, 2))
        top_table.add_column("ID", style="dim", width=14)
        top_table.add_column("Retrievals", justify="right", width=11)
        top_table.add_column("ACT-R", justify="right", width=8)
        top_table.add_column("Fact", max_width=60)
        for fid, hits, fact_text in top_retrieved:
            act = store.activation_score(fid) if fid else 0.0
            top_table.add_row(
                fid or "[dim]deleted[/dim]",
                str(hits),
                f"{act:.3f}" if act > 0 else "[dim]--[/dim]",
                (fact_text or "[dim]deleted[/dim]")[:80],
            )
        console.print(top_table)
        console.print(f"  Total retrievals logged: [bold]{total_retrievals}[/bold]  |  "
                      f"Facts ever accessed: [bold]{facts_with_retrievals}[/bold]  |  "
                      f"Avg ACT-R activation: [bold]{avg_activation:.3f}[/bold]")
        console.print()

    # ---- Creation rate chart ----
    if creation_rows:
        console.print("[bold]Facts added - last 14 days[/bold]  (each [green]*[/green] = 1 fact):")
        max_cnt = max(r[1] for r in creation_rows)
        for day, cnt in creation_rows:
            bar = "[green]" + "*" * cnt + "[/green]"
            console.print(f"  {day}  {bar}  [dim]{cnt}[/dim]")
        console.print()

    # ---- Oldest / newest ----
    if oldest and newest:
        console.print("[bold]Fact age range:[/bold]")
        oldest_date = oldest[2][:10] if oldest[2] else "?"
        newest_date = newest[2][:10] if newest[2] else "?"
        console.print(f"  Oldest:  [dim]{oldest[0]}[/dim]  {oldest_date}  {(oldest[1] or '')[:70]}")
        console.print(f"  Newest:  [dim]{newest[0]}[/dim]  {newest_date}  {(newest[1] or '')[:70]}")
        console.print()

    # ---- Tag breakdown ----
    tag_counter: Counter = Counter()
    untagged = 0
    all_facts_for_tags = store.list_facts(limit=10_000)
    for f in all_facts_for_tags:
        if f.get("tags"):
            tag_counter.update(f["tags"])
        else:
            untagged += 1
    if tag_counter:
        console.print("[bold]Tag distribution:[/bold]  (top 15)")
        tag_table = Table(border_style="dim", padding=(0, 2))
        tag_table.add_column("Tag", style="cyan")
        tag_table.add_column("Facts", justify="right")
        tag_table.add_column("Share", justify="right")
        for t, n in tag_counter.most_common(15):
            pct = 100 * n / fact_count
            tag_table.add_row(t, str(n), f"{pct:.0f}%")
        if untagged:
            tag_table.add_row("[dim](untagged)[/dim]", str(untagged), f"{100*untagged/fact_count:.0f}%")
        console.print(tag_table)
        console.print()


@app.command(name="tag-stats")
def tag_stats(
    top: int = typer.Option(20, "--top", "-n", help="Show top N tags"),
    history: bool = typer.Option(
        False, "--history", help="Show tag growth by month (requires facts with creation dates)"
    ),
) -> None:
    """Show detailed tag analytics: counts, coverage, growth over time.

    Complements `anamne stats` with a tag-specific deep dive:
      - Tag count table with fact count, percentage share, and pinned-fact count
      - Co-occurrence: which tags appear together most often
      - Optional monthly growth breakdown (--history)

    Examples:
      anamne tag-stats
      anamne tag-stats --top 30
      anamne tag-stats --history
    """
    import sqlite3
    import json as _json
    from collections import Counter, defaultdict
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    fact_count = store.fact_count()
    if fact_count == 0:
        console.print("[dim]No facts yet.[/dim]")
        return

    with sqlite3.connect(store._db) as con:
        rows = con.execute(
            "SELECT id, tags, created_at, COALESCE(pinned,0) FROM scratchpad"
        ).fetchall()

    # Parse
    tag_facts: dict = defaultdict(list)
    tag_pinned: Counter = Counter()
    co_occur: dict = defaultdict(Counter)
    month_tags: dict = defaultdict(Counter)  # month -> tag -> count

    for fid, tags_json, created_at, pinned in rows:
        try:
            tags = _json.loads(tags_json)
        except Exception:
            tags = []
        for t in tags:
            tag_facts[t].append(fid)
            if pinned:
                tag_pinned[t] += 1
        # Co-occurrence
        for i, t1 in enumerate(tags):
            for t2 in tags[i+1:]:
                co_occur[t1][t2] += 1
                co_occur[t2][t1] += 1
        # Monthly
        if created_at and history:
            month = created_at[:7]  # YYYY-MM
            for t in tags:
                month_tags[month][t] += 1

    tag_counts: Counter = Counter({t: len(fids) for t, fids in tag_facts.items()})
    untagged = sum(1 for _, tags_json, _, _ in rows if not _json.loads(tags_json or "[]"))

    console.print()
    console.print(f"[bold cyan]Tag Statistics[/bold cyan]  "
                  f"({len(tag_counts)} unique tags, {untagged} untagged facts)\n")

    # Main table
    tbl = Table(border_style="cyan", padding=(0, 2))
    tbl.add_column("Tag", style="cyan")
    tbl.add_column("Facts", justify="right")
    tbl.add_column("Share", justify="right")
    tbl.add_column("Pinned", justify="right")
    tbl.add_column("Co-occurs most with", style="dim")
    for tag_name, cnt in tag_counts.most_common(top):
        pct = 100 * cnt / fact_count
        pinned_cnt = tag_pinned.get(tag_name, 0)
        co_top = ", ".join(
            f"{t}:{n}" for t, n in co_occur[tag_name].most_common(3)
        ) if co_occur[tag_name] else "-"
        tbl.add_row(
            tag_name, str(cnt), f"{pct:.0f}%",
            str(pinned_cnt) if pinned_cnt else "-",
            co_top,
        )
    if untagged:
        tbl.add_row("[dim](untagged)[/dim]", str(untagged),
                    f"{100*untagged/fact_count:.0f}%", "-", "-")
    console.print(tbl)
    console.print()

    # Monthly history
    if history and month_tags:
        console.print("[bold]Monthly tag activity:[/bold]\n")
        for month in sorted(month_tags.keys()):
            top3 = ", ".join(f"{t}:{n}" for t, n in month_tags[month].most_common(3))
            total_in_month = sum(month_tags[month].values())
            console.print(f"  [dim]{month}[/dim]  {total_in_month:3d} tag-uses  {top3}")
        console.print()


def _detect_claude_config_path() -> Optional[Path]:
    """Best-effort detection of the Claude Code config file path."""
    import os
    import platform
    candidates: list[Path] = []
    home = Path.home()
    if platform.system() == "Windows":
        appdata = Path(os.environ.get("APPDATA") or (home / "AppData/Roaming"))
        candidates.append(appdata / "Claude" / "claude_desktop_config.json")
    else:
        # macOS + Linux: Claude Code uses ~/.claude.json or the desktop path
        candidates.append(home / ".claude.json")
        candidates.append(home / "Library/Application Support/Claude/claude_desktop_config.json")
    for c in candidates:
        if c.exists():
            return c
    # Fall back to the first candidate even if it doesn't exist yet
    return candidates[0] if candidates else None


@app.command(name="sync-cloud")
def sync_cloud(
    repo_dir: Path = typer.Option(
        ..., "--repo", "-r",
        help="Path to a local git repo that backs your personal cloud mirror"
    ),
    message: Optional[str] = typer.Option(
        None, "--message", "-m",
        help="Commit message (default: 'anamne sync YYYY-MM-DD')"
    ),
    push: bool = typer.Option(
        True, "--push/--no-push",
        help="Run `git push` after committing (default: yes)"
    ),
    pull: bool = typer.Option(
        False, "--pull",
        help="Pull mode: import from `anamne-export.json` in the repo "
             "(does NOT write or push)"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation prompts in --pull mode"
    ),
) -> None:
    """Two-way bridge between ANAMNE and a personal git mirror.

    Default mode (push):
      Writes `anamne-export.json` inside the local git repo, stages,
      commits, and (by default) pushes. Designed for users who run a
      private GitHub/Gitea/Forgejo repo as a personal cloud sync target.

    --pull mode:
      Reads `anamne-export.json` from the repo and imports it through
      `import-memory` semantics (additive merge - existing facts are not
      deleted; new ones are added). Run `git pull` yourself first.

    Examples:
      anamne sync-cloud --repo ~/anamne-mirror              # push
      anamne sync-cloud --repo ~/anamne-mirror -m "morning sync"
      anamne sync-cloud --repo ~/anamne-mirror --no-push
      anamne sync-cloud --repo ~/anamne-mirror --pull       # ingest
    """
    import subprocess
    from datetime import datetime
    from anamne.store.graph import DecisionStore
    from anamne import __version__

    if not repo_dir.exists():
        console.print(f"[red]Repo directory does not exist: {repo_dir}[/red]")
        raise typer.Exit(code=1)
    if not (repo_dir / ".git").exists():
        console.print(f"[red]{repo_dir} is not a git repo (missing .git/).[/red]")
        raise typer.Exit(code=1)

    store = DecisionStore()

    if pull:
        target = repo_dir / "anamne-export.json"
        if not target.exists():
            console.print(
                f"[red]No anamne-export.json in {repo_dir}.[/red]  "
                "Run `git pull` and try again."
            )
            raise typer.Exit(code=1)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[red]Cannot parse export file:[/red] {e}")
            raise typer.Exit(code=1)
        facts = data.get("scratchpad_facts", []) or []
        decisions = data.get("episodic_decisions", []) or []
        working = data.get("working_memory", []) or []
        console.print(
            f"\n  [yellow]Pull preview:[/yellow] "
            f"{len(facts)} fact(s), {len(decisions)} decision(s), "
            f"{len(working)} working note(s) in the mirror.\n"
        )
        if not yes:
            if not typer.confirm("Merge into local memory?", default=False):
                console.print("[dim]Cancelled.[/dim]\n")
                return

        added_facts = 0
        existing_ids = {f["id"] for f in store.list_facts(limit=100_000)}
        for f in facts:
            try:
                if f.get("id") and f["id"] in existing_ids:
                    continue  # additive merge - skip dupes by id
                new_id = store.remember(
                    f.get("fact") or "",
                    tags=f.get("tags") or [],
                )
                if f.get("pinned") and new_id:
                    store.pin_fact(new_id)
                added_facts += 1
            except Exception:
                pass
        console.print(
            f"  [green]Pulled[/green]  added {added_facts} new fact(s)  "
            f"[dim](existing-by-id duplicates skipped)[/dim]\n"
        )
        return
    payload = {
        "exported_at": datetime.now().isoformat(),
        "version": __version__,
        "scratchpad_facts": store.list_facts(limit=100_000),
        "working_memory": store.working_active(),
        "episodic_decisions": [
            d.to_dict() for d in store.list_all_decisions(limit=100_000)
        ],
    }
    target = repo_dir / "anamne-export.json"
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    console.print(f"  [dim]Wrote[/dim] {target}")

    msg = message or f"anamne sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        subprocess.run(["git", "-C", str(repo_dir), "add", "anamne-export.json"],
                       check=True, capture_output=True, text=True)
        # Skip the commit if there's nothing to add (idempotent sync)
        status = subprocess.run(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            check=True, capture_output=True, text=True,
        )
        if not status.stdout.strip():
            console.print("\n  [dim]No changes - already in sync.[/dim]\n")
            return
        subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", msg],
                       check=True, capture_output=True, text=True)
        console.print(f"  [green]Committed[/green]  {msg}")
        if push:
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "push"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                console.print(
                    f"  [yellow]Push warning:[/yellow] "
                    f"{(result.stderr or result.stdout)[:200]}"
                )
            else:
                console.print("  [green]Pushed[/green]")
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e))[:300]
        console.print(f"  [red]git error:[/red] {err}")
        raise typer.Exit(code=1)
    console.print()


@app.command(name="mcp-config")
def mcp_config(
    client: str = typer.Option(
        "claude", "--client", "-c",
        help="Client: claude | cursor | cline"
    ),
    apply: bool = typer.Option(
        False, "--apply",
        help="Merge the snippet into the detected client config file"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config-path",
        help="Override the auto-detected config file location"
    ),
) -> None:
    """Print or apply a pre-filled MCP config snippet for an AI client.

    Detects the absolute path to the local `anamne` executable so you can drop
    the snippet directly into the client's config file. With `--apply`, the
    Claude / Cline config file is updated in place (the `anamne` MCP server
    entry is merged into `mcpServers`).

    Examples:
      anamne mcp-config                       # print Claude Code snippet
      anamne mcp-config --client cursor
      anamne mcp-config --apply               # merge into ~/.claude.json
      anamne mcp-config --client cline --apply
    """
    import shutil

    cmd_path = shutil.which("anamne") or "anamne"

    if client == "claude":
        snippet = {
            "mcpServers": {
                "anamne": {
                    "command": cmd_path,
                    "args": ["mcp-server"],
                }
            }
        }
        target = "~/.claude.json (macOS/Linux) or %APPDATA%\\Claude\\claude_desktop_config.json"
    elif client == "cursor":
        snippet = {"command": f"{cmd_path} mcp-server"}
        target = "Cursor Settings > MCP > Add server"
    elif client == "cline":
        snippet = {
            "mcpServers": {
                "anamne": {
                    "command": cmd_path,
                    "args": ["mcp-server"],
                }
            }
        }
        target = "Cline VS Code extension settings"
    else:
        console.print(f"[red]Unknown client '{client}'.[/red]  "
                      "Use claude | cursor | cline.")
        raise typer.Exit(code=1)

    if not apply:
        console.print(f"\n  [dim]Paste into:[/dim] {target}\n")
        console.print(json.dumps(snippet, indent=2))
        console.print()
        return

    # --- Apply mode ---
    if client == "cursor":
        console.print(
            "\n  [yellow]--apply not supported for Cursor.[/yellow]  "
            "Open Settings > MCP and paste the snippet manually:\n"
        )
        console.print(json.dumps(snippet, indent=2))
        console.print()
        return

    cfg_path = config_path or _detect_claude_config_path()
    if cfg_path is None:
        console.print("[red]Could not detect a config path. Pass --config-path.[/red]")
        raise typer.Exit(code=1)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if cfg_path.exists():
        try:
            raw = cfg_path.read_text(encoding="utf-8")
            existing = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            console.print(
                f"  [yellow]Existing config is not valid JSON ({e}); "
                "refusing to overwrite.[/yellow]"
            )
            raise typer.Exit(code=1)

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        console.print("[red]Existing mcpServers entry is not an object.[/red]")
        raise typer.Exit(code=1)
    servers["anamne"] = {"command": cmd_path, "args": ["mcp-server"]}
    cfg_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    console.print(
        f"\n  [green]Wrote MCP entry for '[cyan]{client}[/cyan]'[/green]\n"
        f"  [dim]config:[/dim] {cfg_path}\n"
    )


@app.command()
def notebook(
    output: Path = typer.Argument(..., help="Output .ipynb file"),
    tag: list[str] = typer.Option(
        [], "--tag", "-t", help="Filter facts by tag (repeatable)"
    ),
    limit: int = typer.Option(200, "--limit", "-n", help="Max facts to include"),
    runnable: bool = typer.Option(
        False, "--runnable",
        help="Add a code cell at the top that reads back facts via the ANAMNE API"
    ),
) -> None:
    """Export scratchpad facts as a runnable Jupyter notebook.

    Each fact becomes a Markdown cell. Useful for sharing a curated knowledge
    bundle with anyone who has Jupyter installed - no ANAMNE dependency needed.

    With --runnable, the notebook starts with a code cell that uses the
    `anamne` Python API to live-query the same facts (requires ANAMNE installed
    on the reader's machine).

    Examples:
      anamne notebook today.ipynb
      anamne notebook py.ipynb --tag python --limit 100
      anamne notebook py.ipynb --runnable
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    facts = store.list_facts(limit=limit, tags=tag or None)
    if not facts:
        console.print("\n  [dim]No facts to export.[/dim]\n")
        return

    cells: list[dict] = [{
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# ANAMNE memory export\n",
            f"_{len(facts)} fact(s)_"
            + (f"  (tag: {', '.join(tag)})" if tag else "") + "\n",
        ],
    }]

    if runnable:
        tag_filter_py = repr(list(tag)) if tag else "None"
        code_lines = [
            "# Live-query the current ANAMNE memory (re-runs every cell execute).\n",
            "from anamne.store.graph import DecisionStore\n",
            "\n",
            "store = DecisionStore()\n",
            f"facts = store.list_facts(limit={limit}, tags={tag_filter_py})\n",
            "for f in facts:\n",
            "    pin = ' [PIN]' if f.get('pinned') else ''\n",
            "    tag_str = (' #' + ' #'.join(f['tags'])) if f.get('tags') else ''\n",
            "    print(f\"{f['id']}{pin}  {f['fact']}{tag_str}\")\n",
        ]
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": code_lines,
        })

    for f in facts:
        tag_blurb = (
            "  \n*tags: " + ", ".join(f["tags"]) + "*"
            if f.get("tags") else ""
        )
        pin_blurb = "  \n**[pinned]**" if f.get("pinned") else ""
        cells.append({
            "cell_type": "markdown",
            "metadata": {"anamne_id": f["id"]},
            "source": [
                f"### `{f['id']}`\n",
                f"{f['fact']}{tag_blurb}{pin_blurb}",
            ],
        })

    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3", "language": "python", "name": "python3"
            },
            "language_info": {"name": "python"},
            "anamne_export": {"facts": len(facts)},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    output.write_text(json.dumps(nb, indent=2), encoding="utf-8")
    console.print(f"\n  [green]Notebook written[/green]  [bold]{output}[/bold]  "
                  f"[dim]({len(facts)} fact(s))[/dim]\n")


@app.command()
def tools(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    schema: Optional[str] = typer.Option(
        None, "--schema", "-s", metavar="TOOL_NAME",
        help="Dump the full JSON schema for a specific tool"
    ),
) -> None:
    """List every tool the MCP server would expose to AI clients.

    Useful for verifying which capabilities are wired up before connecting
    Claude Code / Cursor / Cline.

    Examples:
      anamne tools
      anamne tools --json
    """
    from anamne.mcp.server import mcp

    # FastMCP keeps tool definitions on the server; introspect via list_tools()
    try:
        # FastMCP exposes a sync `list_tools()` helper on its tool manager
        registry = getattr(mcp, "_tool_manager", None) or mcp
        items = []
        # Try several attribute names since FastMCP version may vary
        listed = []
        if hasattr(registry, "list_tools_sync"):
            listed = registry.list_tools_sync()
        elif hasattr(registry, "list_tools"):
            try:
                import inspect
                res = registry.list_tools()
                if inspect.iscoroutine(res):
                    import asyncio
                    listed = asyncio.run(res)
                else:
                    listed = res
            except Exception:
                listed = []
        if not listed and hasattr(mcp, "_tools"):
            listed = list(mcp._tools.values())
        for t in listed or []:
            name = getattr(t, "name", None) or (
                t.get("name") if isinstance(t, dict) else str(t)
            )
            desc = getattr(t, "description", None) or (
                t.get("description") if isinstance(t, dict) else ""
            )
            # FastMCP may expose parameters / inputSchema differently per version
            params = (
                getattr(t, "inputSchema", None)
                or getattr(t, "parameters", None)
                or (t.get("inputSchema") if isinstance(t, dict) else None)
                or (t.get("parameters") if isinstance(t, dict) else None)
            )
            items.append({
                "name": name,
                "description": (desc or "").strip(),
                "parameters": params,
            })
    except Exception as e:
        console.print(f"[red]Could not introspect MCP tools:[/red] {e}")
        raise typer.Exit(code=1)

    if not items:
        console.print("\n  [dim]No MCP tools detected.[/dim]\n")
        return

    if schema:
        match = next((it for it in items if it["name"] == schema), None)
        if not match:
            console.print(f"[yellow]No MCP tool named '{schema}'.[/yellow]")
            raise typer.Exit(code=1)
        console.print(json.dumps(match, indent=2, default=str))
        return

    if as_json:
        # Drop parameter blobs from the summary view to keep it compact
        summary = [
            {"name": it["name"], "description": it["description"]}
            for it in items
        ]
        console.print(json.dumps(summary, indent=2))
        return

    console.print(f"\n  [bold]{len(items)} MCP tool(s):[/bold]\n")
    for it in items:
        first_line = (it["description"] or "").splitlines()[0][:80]
        console.print(f"  [cyan]{it['name']:30}[/cyan]  [dim]{first_line}[/dim]")
    console.print()


@app.command()
def mcp_server() -> None:
    """Start the MCP server - connects anamne to Cursor / Claude Code.

    IMPORTANT: MCP uses stdio for JSON-RPC. We must NOT write anything to
    stdout other than the protocol itself, or the host (Claude Code, Cursor)
    will fail to parse the handshake. Status messages go to stderr.
    """
    import sys
    from anamne.config import get_settings

    cfg = get_settings()
    if not (cfg.anthropic_api_key or cfg.gemini_api_key):
        # Stderr-only  - must not pollute stdout
        sys.stderr.write(
            "anamne MCP: no LLM API key configured.\n"
            "Run `anamne init` first, then restart your MCP host.\n"
        )
        raise typer.Exit(1)

    sys.stderr.write(
        f"anamne MCP server starting (model: {cfg.resolved_model()})\n"
    )
    sys.stderr.flush()

    from anamne.mcp.server import run
    run()


@app.command()
def diff(
    id1: str = typer.Argument(..., help="First fact id"),
    id2: Optional[str] = typer.Argument(None, help="Second fact id (omit if --history)"),
    history: bool = typer.Option(
        False, "--history",
        help="Compare id1's current content against the previous history version"
    ),
) -> None:
    """Compare two scratchpad facts side-by-side (text, tags, activation).

    With --history, compares id1's current state against its most recent
    archived version in fact_history (instead of needing a second id).

    Examples:
      anamne diff abc123 def456
      anamne diff abc123 --history
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    a = store.get_fact(id1)
    if a is None:
        console.print(f"[red]No fact found with id '{id1}'.[/red]")
        raise typer.Exit(code=1)

    if history:
        hist = store.get_fact_history(id1)
        # Most recent entry that has non-empty content and is not the synthetic
        # "current state" row some implementations record on every change.
        old = None
        for h in reversed(hist):
            if h.get("content") and h.get("change_type") != "current":
                old = h
                break
        if old is None:
            console.print(f"[dim]No prior history for fact {id1}.[/dim]")
            return
        try:
            old_tags = json.loads(old.get("tags") or "[]")
        except Exception:
            old_tags = []
        b = {
            "id": f"history@{old.get('changed_at', '')[:19]}",
            "fact": old.get("content") or "",
            "tags": old_tags,
            "created_at": old.get("changed_at") or "",
            "last_used_at": old.get("changed_at") or "",
            "use_count": 0,
            "pinned": False,
        }
    else:
        if id2 is None:
            console.print(
                "[red]Provide a second fact id, or use --history.[/red]"
            )
            raise typer.Exit(code=1)
        b = store.get_fact(id2)
        if b is None:
            console.print(f"[red]No fact found with id '{id2}'.[/red]")
            raise typer.Exit(code=1)

    act_a = store.activation_score(a["id"])
    try:
        act_b = store.activation_score(b["id"]) if not history else 0.0
    except Exception:
        act_b = 0.0
    tags_a = ", ".join(a.get("tags") or []) or "-"
    tags_b = ", ".join(b.get("tags") or []) or "-"

    table = Table(border_style="cyan", padding=(0, 2))
    table.add_column("", style="dim", no_wrap=True, width=14)
    table.add_column(a["id"], style="cyan")
    table.add_column(b["id"], style="cyan")
    table.add_row("Fact", a["fact"], b["fact"])
    table.add_row("Tags", tags_a, tags_b)
    table.add_row("Created", a["created_at"][:19], b["created_at"][:19])
    table.add_row("Last used", a["last_used_at"][:19], b["last_used_at"][:19])
    table.add_row("Use count", str(a["use_count"]), str(b["use_count"]))
    table.add_row("ACT-R", f"{act_a:.4f}", f"{act_b:.4f}")
    table.add_row(
        "Pinned",
        "yes" if a.get("pinned") else "no",
        "yes" if b.get("pinned") else "no",
    )
    # Simple identical-text marker
    table.add_row(
        "Identical text",
        "[green]yes[/green]" if a["fact"] == b["fact"] else "[dim]no[/dim]",
        "",
    )
    console.print()
    console.print(table)
    console.print()


@app.command(name="fact-of-the-day")
def fact_of_the_day(
    post_to: Optional[str] = typer.Option(
        None, "--post-to", metavar="URL",
        help="POST the fact as JSON to a webhook (Slack-style payloads supported)"
    ),
) -> None:
    """Surface one fact at random from pinned + top-activation facts.

    Designed to be called on shell login or before a coding session - quick
    reminder of something durable. Touches the fact for ACT-R activation.

    With `--post-to`, sends a JSON POST to the URL. The payload includes
    `{id, fact, tags, pinned, text}` where `text` is a pre-formatted message
    (works with Slack/Discord-style hooks that accept `text`).

    Examples:
      anamne fact-of-the-day
      anamne fact-of-the-day --post-to https://hooks.slack.com/services/...
    """
    import random
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    all_facts = store.list_facts(limit=10_000)
    if not all_facts:
        console.print("\n  [dim]No facts yet.[/dim]\n")
        return
    pinned = [f for f in all_facts if f.get("pinned")]
    # Top 20 by activation among unpinned
    scored = sorted(
        ((store.activation_score(f["id"]), f) for f in all_facts if not f.get("pinned")),
        key=lambda x: x[0], reverse=True,
    )
    top = [f for _, f in scored[:20]]
    pool = pinned + top
    if not pool:
        pool = all_facts
    chosen = random.choice(pool)
    tag_str = (", ".join(chosen["tags"]) or "-")
    console.print()
    console.print("  [bold]Fact of the day[/bold]")
    console.print(
        f"  [cyan]{chosen['id']}[/cyan]  {chosen['fact']}\n"
        f"  [dim]tags:[/dim] {tag_str}"
        f"{'  [yellow][pinned][/yellow]' if chosen.get('pinned') else ''}"
    )
    console.print()
    try:
        store.touch_facts([chosen["id"]])
    except Exception:
        pass

    if post_to:
        import httpx
        prefix = "[pinned] " if chosen.get("pinned") else ""
        text = f"{prefix}{chosen['fact']}  (tags: {tag_str})"
        payload = {
            "id": chosen["id"],
            "fact": chosen["fact"],
            "tags": chosen.get("tags") or [],
            "pinned": bool(chosen.get("pinned")),
            "text": text,  # Slack/Discord-style consumers usually want `text`
        }
        try:
            resp = httpx.post(post_to, json=payload, timeout=10.0)
            if resp.status_code >= 400:
                console.print(
                    f"  [yellow]Webhook returned {resp.status_code}: "
                    f"{resp.text[:120]}[/yellow]\n"
                )
            else:
                console.print(f"  [green]Posted to webhook[/green]  "
                              f"[dim]({resp.status_code})[/dim]\n")
        except Exception as e:
            console.print(f"  [red]Webhook failed:[/red] {e}\n")


def _templates_path() -> Path:
    """Location of the JSON file backing `anamne template`."""
    p = Path.home() / ".anamne" / "templates.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("{}", encoding="utf-8")
    return p


def _load_templates() -> dict:
    try:
        return json.loads(_templates_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_templates(data: dict) -> None:
    _templates_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


@app.command()
def template(
    action: str = typer.Argument(
        ..., help="Action: add | list | show | use | remove | export | import"
    ),
    name: Optional[str] = typer.Argument(None, help="Template name (for add/use/remove)"),
    body: Optional[str] = typer.Argument(
        None, help="Template body (for add) or substitution value (for use)"
    ),
    tag: list[str] = typer.Option(
        [], "--tag", "-t", help="Tags to attach when using a template"
    ),
) -> None:
    """Manage named text templates for fast structured fact entry.

    Templates store reusable Python-style format strings. Use `{x}` placeholders
    in the body; provide their values via `--var KEY=VAL` (or as positional body
    text when there is exactly one placeholder).

    Examples:
      anamne template add decision "Decision: {what}. Why: {why}."
      anamne template list
      anamne template use decision "Use Postgres. Why: concurrent writes." --tag db
      anamne template remove decision

    Notes:
      - For the `use` action, the `body` positional is the substitution text:
        - If the template has exactly one `{x}` placeholder it is substituted
          verbatim.
        - Otherwise the entire template body is treated as a prefix and the
          `body` text is appended after a space.
      - Templates are stored at ~/.anamne/templates.json (plain JSON, edit by hand
        if you prefer).
    """
    from anamne.store.graph import DecisionStore

    templates = _load_templates()

    if action == "list":
        if not templates:
            console.print("\n  [dim]No templates defined.[/dim]\n")
            return
        console.print(f"\n  [bold]{len(templates)} template(s):[/bold]\n")
        for k, v in sorted(templates.items()):
            console.print(f"  [cyan]{k:20}[/cyan]  {v}")
        console.print()
        return

    if action == "add":
        if not name or not body:
            console.print("[red]usage: anamne template add <name> \"<body>\"[/red]")
            raise typer.Exit(code=1)
        templates[name] = body
        _save_templates(templates)
        console.print(f"\n  [green]Saved template[/green]  [cyan]{name}[/cyan]  -  "
                      f"{body[:80]}\n")
        return

    if action == "remove":
        if not name:
            console.print("[red]usage: anamne template remove <name>[/red]")
            raise typer.Exit(code=1)
        if name not in templates:
            console.print(f"[yellow]No template named '{name}'.[/yellow]")
            raise typer.Exit(code=1)
        del templates[name]
        _save_templates(templates)
        console.print(f"\n  [green]Removed[/green]  [cyan]{name}[/cyan]\n")
        return

    if action == "show":
        if not name:
            console.print("[red]usage: anamne template show <name>[/red]")
            raise typer.Exit(code=1)
        if name not in templates:
            console.print(f"[yellow]No template named '{name}'.[/yellow]")
            raise typer.Exit(code=1)
        console.print(f"\n  [cyan]{name}[/cyan]\n")
        console.print(templates[name])
        console.print()
        return

    if action == "export":
        if not name:
            console.print("[red]usage: anamne template export <output-file>[/red]")
            raise typer.Exit(code=1)
        Path(name).write_text(
            json.dumps(templates, indent=2), encoding="utf-8"
        )
        console.print(f"\n  [green]Exported {len(templates)} template(s)[/green]  "
                      f"-> {name}\n")
        return

    if action == "import":
        if not name:
            console.print("[red]usage: anamne template import <input-file>[/red]")
            raise typer.Exit(code=1)
        try:
            incoming = json.loads(Path(name).read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[red]Failed to read templates file:[/red] {e}")
            raise typer.Exit(code=1)
        if not isinstance(incoming, dict):
            console.print("[red]Template file must be a JSON object {name: body}[/red]")
            raise typer.Exit(code=1)
        added, replaced = 0, 0
        for k, v in incoming.items():
            if not isinstance(v, str):
                continue
            if k in templates:
                replaced += 1
            else:
                added += 1
            templates[k] = v
        _save_templates(templates)
        console.print(
            f"\n  [green]Imported[/green]  "
            f"{added} new, {replaced} replaced.  "
            f"Total templates: [bold]{len(templates)}[/bold]\n"
        )
        return

    if action == "use":
        if not name:
            console.print("[red]usage: anamne template use <name> \"<text>\" "
                          "[--tag X][/red]")
            raise typer.Exit(code=1)
        if name not in templates:
            console.print(f"[yellow]No template named '{name}'.[/yellow]")
            raise typer.Exit(code=1)
        tmpl = templates[name]
        # Count placeholders
        import string
        formatter = string.Formatter()
        placeholders = [
            fname for _, fname, _, _ in formatter.parse(tmpl)
            if fname is not None and fname != ""
        ]
        if len(placeholders) == 1 and body is not None:
            try:
                final = tmpl.format(**{placeholders[0]: body})
            except KeyError:
                final = f"{tmpl} {body}"
        elif body:
            final = f"{tmpl} {body}"
        else:
            final = tmpl

        store = DecisionStore()
        mid = store.remember(final, tags=tag or None)
        console.print(
            f"\n  [green]Stored via template[/green]  [cyan]{mid}[/cyan]\n"
            f"  {final}\n"
        )
        return

    console.print(
        f"[red]Unknown action '{action}'. "
        "Use add | list | show | use | remove | export | import.[/red]"
    )
    raise typer.Exit(code=1)


@app.command()
def quiz(
    count: int = typer.Option(3, "--count", "-n", help="Number of questions"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Restrict to facts with this tag"),
    grade: bool = typer.Option(
        False, "--grade", "-g",
        help="Interactive: ask the user, then LLM-grade each answer"
    ),
    difficulty: str = typer.Option(
        "normal", "--difficulty", "-d",
        help="Difficulty: easy | normal | hard"
    ),
    resume: bool = typer.Option(
        False, "--resume",
        help="Continue an unfinished quiz session (uses ~/.anamne/quiz-state.json)"
    ),
) -> None:
    """LLM-driven Q&A drill against your scratchpad facts.

    Picks N random facts and asks the LLM to write one question per fact. By
    default the answer is shown immediately. With --grade, the shell prompts
    for the user's answer and the LLM scores correctness (correct / partial /
    wrong) with a one-line reason.

    Touches the source facts for ACT-R activation. Useful for spaced
    repetition / self-quiz of durable knowledge.

    Examples:
      anamne quiz
      anamne quiz --count 5 --grade
      anamne quiz --tag architecture --count 3 --grade
    """
    import random
    from anamne.store.graph import DecisionStore
    from anamne.llm import LLMClient

    quiz_state_path = Path.home() / ".anamne" / "quiz-state.json"

    store = DecisionStore()

    sample: list[dict] = []
    seen_ids: set[str] = set()

    if resume and quiz_state_path.exists():
        try:
            state = json.loads(quiz_state_path.read_text(encoding="utf-8"))
            pending = state.get("pending", [])
            seen_ids = set(state.get("seen", []))
            # Re-hydrate facts by id (skip any since-deleted)
            for fid in pending:
                f = store.get_fact(fid)
                if f is not None:
                    sample.append(f)
            if not sample:
                console.print(
                    "\n  [dim]No pending quiz items to resume; starting fresh.[/dim]\n"
                )
        except Exception:
            sample = []

    if not sample:
        pool = store.list_facts(limit=10_000, tags=tag or None)
        if not pool:
            console.print("\n  [dim]No facts to quiz on.[/dim]\n")
            return
        sample = random.sample(pool, min(count, len(pool)))
        seen_ids = set()

    try:
        client = LLMClient()
    except Exception as e:
        console.print(f"  [red]LLM unavailable:[/red] {e}")
        raise typer.Exit(code=1)

    correct_count = 0
    partial_count = 0
    wrong_count = 0

    diff_clauses = {
        "easy": (
            "The question should be a direct recall question - test whether the "
            "user can remember the fact verbatim."
        ),
        "hard": (
            "The question must require synthesis or application, not direct "
            "recall. Phrase it so the surface wording differs significantly "
            "from the fact, and the user has to reason about why or when the "
            "fact applies."
        ),
        "normal": (
            "The question should be a clear comprehension check at moderate "
            "difficulty."
        ),
    }
    diff_clause = diff_clauses.get(difficulty.lower(), diff_clauses["normal"])

    def _save_state(pending_facts: list[dict]) -> None:
        try:
            quiz_state_path.parent.mkdir(parents=True, exist_ok=True)
            quiz_state_path.write_text(
                json.dumps({
                    "pending": [pf["id"] for pf in pending_facts],
                    "seen": sorted(seen_ids),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _clear_state() -> None:
        try:
            if quiz_state_path.exists():
                quiz_state_path.unlink()
        except Exception:
            pass

    console.print(f"\n  [bold]Quiz[/bold]  [dim]({len(sample)} question(s)"
                  f"{' - interactive grading' if grade else ''}"
                  f", difficulty={difficulty}"
                  f"{', resumed' if resume else ''})[/dim]\n")
    interrupted = False
    for i, f in enumerate(sample, start=1):
        # Update state to reflect remaining work BEFORE processing this question.
        # On Ctrl-C, the current item is the next "pending" item to resume.
        _save_state(sample[i - 1:])
        prompt = (
            "Write one short quiz question about the fact below, then on a "
            "new line write the one-sentence answer. " + diff_clause + " "
            "Reply EXACTLY in this format:\n"
            "Q: <question>\nA: <answer>\n\n"
            f"FACT: {f['fact']}"
        )
        try:
            raw = client.complete(prompt, max_tokens=200).text.strip()
        except Exception as e:
            console.print(f"  [yellow]LLM error: {e}[/yellow]")
            seen_ids.add(f["id"])
            continue
        q_line, a_line = "", ""
        for ln in raw.splitlines():
            if ln.lower().startswith("q:"):
                q_line = ln[2:].strip()
            elif ln.lower().startswith("a:"):
                a_line = ln[2:].strip()
        if not q_line or not a_line:
            console.print(f"  [bold]Q{i}.[/bold] {raw}\n")
            seen_ids.add(f["id"])
            continue

        console.print(f"  [bold]Q{i}.[/bold] {q_line}")
        if not grade:
            console.print(f"      [dim]A:[/dim] {a_line}")
            console.print(f"      [dim]from:[/dim] [cyan]{f['id']}[/cyan]")
            console.print()
            seen_ids.add(f["id"])
            continue

        # Interactive grading
        try:
            user_answer = input("    your answer> ").strip()
        except (EOFError, KeyboardInterrupt):
            # Keep this fact as still-pending so --resume picks it up.
            _save_state(sample[i - 1:])
            console.print(
                "\n  [dim]quiz interrupted - run [bold]anamne quiz --resume"
                "[/bold] to continue[/dim]\n"
            )
            interrupted = True
            break
        if not user_answer:
            console.print(f"      [dim]skipped[/dim]  expected: {a_line}\n")
            continue
        grade_prompt = (
            "Grade the USER ANSWER against the REFERENCE ANSWER. Reply EXACTLY "
            "in this format on ONE line:\n"
            "VERDICT: <correct|partial|wrong> | REASON: <one short sentence>\n\n"
            f"QUESTION: {q_line}\n"
            f"REFERENCE ANSWER: {a_line}\n"
            f"USER ANSWER: {user_answer}\n"
            f"SOURCE FACT: {f['fact']}"
        )
        try:
            grade_raw = client.complete(grade_prompt, max_tokens=120).text.strip()
        except Exception as e:
            grade_raw = f"VERDICT: wrong | REASON: grading failed ({e})"
        verdict = "wrong"
        reason = grade_raw
        if "VERDICT:" in grade_raw:
            after = grade_raw.split("VERDICT:", 1)[1]
            verdict = after.split("|")[0].strip().lower()
            if "REASON:" in after:
                reason = after.split("REASON:", 1)[1].strip()
        if verdict.startswith("correct"):
            correct_count += 1
            colour = "green"
        elif verdict.startswith("partial"):
            partial_count += 1
            colour = "yellow"
        else:
            wrong_count += 1
            colour = "red"
        console.print(f"      [{colour}]{verdict.upper()}[/{colour}]  {reason}")
        console.print(f"      [dim]reference:[/dim] {a_line}")
        console.print(f"      [dim]from:[/dim] [cyan]{f['id']}[/cyan]\n")
        seen_ids.add(f["id"])

    if not interrupted:
        _clear_state()

    if grade and (correct_count + partial_count + wrong_count) > 0:
        total = correct_count + partial_count + wrong_count
        console.print(
            f"  [bold]Result:[/bold]  "
            f"[green]{correct_count} correct[/green]   "
            f"[yellow]{partial_count} partial[/yellow]   "
            f"[red]{wrong_count} wrong[/red]   "
            f"[dim](of {total})[/dim]\n"
        )

    try:
        store.touch_facts([f["id"] for f in sample])
    except Exception:
        pass


@app.command(name="random")
def random_facts(
    count: int = typer.Argument(5, help="How many random facts to surface"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag"),
    pinned_only: bool = typer.Option(False, "--pinned", help="Only sample from pinned facts"),
) -> None:
    """Pull N random scratchpad facts for review or self-quiz.

    Touches each surfaced fact (ACT-R activation bump).

    Examples:
      anamne random 5
      anamne random 10 --tag python
      anamne random 3 --pinned
    """
    import random
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    pool = store.list_facts(limit=10_000, tags=tag or None)
    if pinned_only:
        pool = [f for f in pool if f.get("pinned")]
    if not pool:
        console.print("\n  [dim]No facts in the requested pool.[/dim]\n")
        return
    sample = random.sample(pool, min(count, len(pool)))
    console.print(f"\n  [bold]{len(sample)} random fact(s):[/bold]\n")
    for f in sample:
        pin = " [yellow]*[/yellow]" if f.get("pinned") else ""
        console.print(f"  [cyan]{f['id']}[/cyan]{pin}  {f['fact']}")
        if f.get("tags"):
            console.print(f"      [dim]tags:[/dim] {', '.join(f['tags'])}")
    console.print()
    try:
        store.touch_facts([f["id"] for f in sample])
    except Exception:
        pass


@app.command()
def backup(
    output_dir: Optional[Path] = typer.Option(
        None, "--dir", "-d", help="Backup directory (default ~/.anamne/backups)"
    ),
    keep: int = typer.Option(
        0, "--keep", "-k",
        help="Keep only the N newest backups; older files are deleted (0 = no rotation)"
    ),
) -> None:
    """One-shot timestamped JSON backup of every memory layer.

    Writes `<dir>/anamne-backup-YYYYMMDD-HHMMSS.json` and prints the path.
    The backup is the same shape as `anamne export --output ...` so it can be
    restored with `anamne import-memory`.

    With `--keep N`, older backups in the same directory are removed after the
    new one is written. Useful in a cron loop.

    Examples:
      anamne backup
      anamne backup --dir ./my-backups
      anamne backup --keep 7              # daily backup, retain one week
    """
    from datetime import datetime
    from anamne.store.graph import DecisionStore
    from anamne import __version__

    store = DecisionStore()
    target_dir = output_dir or (Path.home() / ".anamne" / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"anamne-backup-{stamp}.json"

    payload = {
        "exported_at": stamp,
        "version": __version__,
        "scratchpad_facts": store.list_facts(limit=100_000),
        "working_memory": store.working_active(),
        "episodic_decisions": [
            d.to_dict() for d in store.list_all_decisions(limit=100_000)
        ],
    }
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    size_kb = target.stat().st_size / 1024
    console.print(
        f"\n  [green]Backup written[/green]  [bold]{target}[/bold]  "
        f"[dim]({size_kb:.1f} KB)[/dim]"
    )

    if keep and keep > 0:
        existing = sorted(
            target_dir.glob("anamne-backup-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        to_remove = existing[keep:]
        for p in to_remove:
            try:
                p.unlink()
            except Exception:
                pass
        if to_remove:
            console.print(
                f"  [dim]Rotated[/dim] {len(to_remove)} older backup(s); "
                f"keeping the newest {keep}."
            )
    console.print()


@app.command()
def merge(
    keep_id: str = typer.Argument(..., help="Fact ID to keep (will hold merged content)"),
    drop_id: str = typer.Argument(..., help="Fact ID to delete (its content is merged in)"),
    use_llm: bool = typer.Option(
        False, "--llm",
        help="Use the LLM to write a merged sentence (default: concatenate with '. ')"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d",
        help="Show the proposed merge without applying it"
    ),
) -> None:
    """Manually merge two scratchpad facts into one.

    Workflow:
      1. The two fact texts are combined (either via LLM rewrite or simple
         concatenation).
      2. Tags from both facts are unioned and applied to `keep_id`.
      3. `drop_id` is deleted; a `merged_into` history entry points to `keep_id`.

    Unlike `anamne consolidate`, this is a targeted user-driven merge - no
    clustering, no auto-detection.

    Examples:
      anamne merge abc123 def456
      anamne merge abc123 def456 --llm
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    a = store.get_fact(keep_id)
    b = store.get_fact(drop_id)
    if a is None or b is None:
        missing = keep_id if a is None else drop_id
        console.print(f"[red]No fact found with id '{missing}'.[/red]")
        raise typer.Exit(code=1)
    if keep_id == drop_id:
        console.print("[yellow]keep_id and drop_id must be different.[/yellow]")
        raise typer.Exit(code=1)

    merged_text: str
    if use_llm:
        try:
            from anamne.llm import LLMClient
            client = LLMClient()
            prompt = (
                "Merge the following two related facts into a single concise "
                "sentence preserving every distinct claim. Reply with ONLY the "
                "merged sentence, no quotes, no prose.\n\n"
                f"A: {a['fact']}\nB: {b['fact']}\nMERGED:"
            )
            merged_text = client.complete(prompt, max_tokens=160).text.strip()
            if not merged_text:
                merged_text = f"{a['fact']}. {b['fact']}"
        except Exception as e:
            console.print(f"  [yellow]LLM unavailable ({e}); falling back to "
                          "concatenation.[/yellow]")
            merged_text = f"{a['fact']}. {b['fact']}"
    else:
        merged_text = f"{a['fact']}. {b['fact']}"

    merged_tags = sorted(set((a.get("tags") or []) + (b.get("tags") or [])))

    if dry_run:
        console.print(
            f"\n  [bold]Dry run - no changes applied[/bold]\n\n"
            f"  [dim]keep:[/dim]    [cyan]{keep_id}[/cyan]\n"
            f"  [dim]drop:[/dim]    [cyan]{drop_id}[/cyan]\n"
            f"  [dim]merged:[/dim]  {merged_text}\n"
            f"  [dim]tags:[/dim]    {', '.join(merged_tags) or '-'}\n\n"
            f"  Re-run without [bold]--dry-run[/bold] to apply.\n"
        )
        return

    # Update content + tags on the keeper
    store.update_fact_content(keep_id, merged_text)
    store.update_fact_tags(keep_id, set_tags=merged_tags)
    # Delete the donor, leaving a merged_into history breadcrumb
    store.forget_fact(drop_id, _merged_into=keep_id)

    console.print(
        f"\n  [green]Merged[/green]\n"
        f"  [dim]kept:[/dim]   [cyan]{keep_id}[/cyan]  {merged_text[:80]}\n"
        f"  [dim]tags:[/dim]   {', '.join(merged_tags) or '-'}\n"
        f"  [dim]dropped:[/dim] [cyan]{drop_id}[/cyan] (history -> {keep_id})\n"
    )


@app.command()
def stash(
    text: Optional[str] = typer.Argument(None, help="Note to stash (omit to list)"),
    list_all: bool = typer.Option(False, "--list", "-l",
                                  help="List active stash items"),
    promote_id: Optional[str] = typer.Option(
        None, "--promote", "-p", metavar="WORKING_ID",
        help="Promote a stashed item to a permanent scratchpad fact"
    ),
    clear: bool = typer.Option(False, "--clear", help="Delete all active stash items"),
) -> None:
    """Quick-jot working memory notes (tagged 'stash' for easy lookup).

    `anamne stash "..."` is shorthand for `anamne working "..."`, with the
    convention that stashed items represent ephemeral context you may want to
    promote later. Stash items expire on the working memory TTL (60 min).

    Examples:
      anamne stash "investigate webhook double-fire after 3pm"
      anamne stash --list
      anamne stash --promote abc123
      anamne stash --clear
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()

    if promote_id:
        new_id = store.promote_working(promote_id, tags=["stash-promoted"])
        if new_id is None:
            console.print(f"[red]No working note with id '{promote_id}'.[/red]")
            raise typer.Exit(code=1)
        console.print(
            f"\n  [green]Promoted[/green] stash [dim]{promote_id}[/dim] "
            f"-> scratchpad [cyan]{new_id}[/cyan]\n"
        )
        return

    if clear:
        # Remove only stash-tagged working notes
        active = store.working_active()
        # Working notes don't have tags; rely on the convention that we
        # created them via this command. Use working_delete on all that
        # match a [stash] prefix marker.
        deleted = 0
        for w in active:
            if w["note"].startswith("[stash] "):
                store.working_delete(w["id"])
                deleted += 1
        console.print(f"\n  [green]Cleared {deleted} stash item(s).[/green]\n")
        return

    if list_all or not text:
        items = [w for w in store.working_active() if w["note"].startswith("[stash] ")]
        if not items:
            console.print("\n  [dim]No active stash items.[/dim]\n")
            return
        console.print(f"\n  [bold]{len(items)} stash item(s):[/bold]\n")
        for w in items:
            exp = (w.get("expires_at") or "")[:19]
            body = w["note"][len("[stash] "):]
            console.print(f"  [cyan]{w['id']}[/cyan]  {body}\n      "
                          f"[dim]expires {exp}[/dim]")
        console.print()
        return

    # Default: add new stash item
    wid = store.working_add(f"[stash] {text}")
    console.print(f"\n  [green]Stashed[/green] [cyan]{wid}[/cyan]  -  "
                  f"{text[:80]}\n")


@app.command()
def snapshot(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Write to file (default: print to stdout)"
    ),
    limit: int = typer.Option(50, "--limit", "-n",
                              help="Max facts per section"),
    as_html: bool = typer.Option(
        False, "--html", help="Emit minimal HTML instead of Markdown"
    ),
) -> None:
    """Print a compact human-readable Markdown snapshot of your memory.

    Sections:
      - Pinned facts
      - Top-activation unpinned facts
      - Recently added facts (last 7 days)
      - Active working memory

    Useful for pasting into a chat or a daily standup doc.

    Examples:
      anamne snapshot
      anamne snapshot --output today.md
      anamne snapshot --limit 30
    """
    from datetime import datetime, timezone, timedelta
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    all_facts = store.list_facts(limit=10_000)
    pinned = [f for f in all_facts if f.get("pinned")]
    unpinned_scored = sorted(
        ((store.activation_score(f["id"]), f) for f in all_facts if not f.get("pinned")),
        key=lambda x: x[0], reverse=True,
    )
    top_unpinned = [f for _, f in unpinned_scored[:limit]]
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_facts = sorted(
        [f for f in all_facts if (f.get("created_at") or "") >= week_ago],
        key=lambda f: f.get("created_at") or "",
        reverse=True,
    )[:limit]
    working = store.working_active()[:limit]

    lines: list[str] = ["# ANAMNE memory snapshot",
                        f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]

    lines.append(f"## Pinned ({len(pinned)})\n")
    if pinned:
        for f in pinned:
            tag_str = (" `#" + "` `#".join(f["tags"]) + "`") if f["tags"] else ""
            lines.append(f"- {f['fact']}{tag_str}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append(f"## Top activation ({len(top_unpinned)})\n")
    if top_unpinned:
        for f in top_unpinned:
            tag_str = (" `#" + "` `#".join(f["tags"]) + "`") if f["tags"] else ""
            lines.append(f"- {f['fact']}{tag_str}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append(f"## Recent - last 7 days ({len(recent_facts)})\n")
    if recent_facts:
        for f in recent_facts:
            day = (f.get("created_at") or "")[:10]
            lines.append(f"- _{day}_  {f['fact']}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append(f"## Working ({len(working)})\n")
    if working:
        for w in working:
            exp = (w.get("expires_at") or "")[:19]
            lines.append(f"- {w['note']} _(expires {exp})_")
    else:
        lines.append("_None._")
    lines.append("")

    text = "\n".join(lines)

    if as_html:
        # Minimal HTML wrapper - escape and convert basic Markdown lists
        import html as _html
        def _md_to_html(md: str) -> str:
            out: list[str] = []
            in_list = False
            for ln in md.splitlines():
                escaped = _html.escape(ln)
                if escaped.startswith("# "):
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append(f"<h1>{escaped[2:]}</h1>")
                elif escaped.startswith("## "):
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append(f"<h2>{escaped[3:]}</h2>")
                elif escaped.startswith("- "):
                    if not in_list:
                        out.append("<ul>"); in_list = True
                    out.append(f"<li>{escaped[2:]}</li>")
                elif escaped.strip().startswith("_") and escaped.strip().endswith("_"):
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append(f"<p><em>{escaped.strip().strip('_')}</em></p>")
                elif escaped.strip() == "":
                    if in_list:
                        out.append("</ul>"); in_list = False
                else:
                    out.append(f"<p>{escaped}</p>")
            if in_list:
                out.append("</ul>")
            return "\n".join(out)

        body = _md_to_html(text)
        text = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>ANAMNE snapshot</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:780px;"
            "margin:2rem auto;padding:0 1rem;color:#222;}"
            "h1,h2{border-bottom:1px solid #ddd;padding-bottom:.2em;}"
            "li{margin:.25em 0;}code{background:#f4f4f4;padding:0 .25em;"
            "border-radius:3px;}</style></head><body>\n"
            f"{body}\n</body></html>"
        )

    if output:
        output.write_text(text, encoding="utf-8")
        console.print(f"\n  [green]Snapshot written[/green]  [bold]{output}[/bold]\n")
    else:
        # Use plain print so the output survives stdout redirection
        print(text)


@app.command(name="search-all")
def search_all(
    query: str = typer.Argument(..., help="Search term"),
    limit: int = typer.Option(5, "--limit", "-n",
                              help="Max results PER LAYER (default 5)"),
) -> None:
    """Search across all three memory layers in one shot.

    Returns up to `--limit` results each from:
      - Scratchpad (ACT-R ranked hybrid search)
      - Episodic decisions (ChromaDB semantic search)
      - Working memory (substring + semantic)

    A fast cross-layer scan when you don't know where the answer lives.

    Examples:
      anamne search-all postgres
      anamne search-all "auth design" --limit 3
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()

    # Scratchpad
    scratch = store.search_facts_ranked(query, limit=limit)
    # Episodic
    episodic = store.search(query, n_results=limit)
    # Working
    work = store.search_working(query, limit=limit)

    if not (scratch or episodic or work):
        console.print(f"\n  [dim]No results across any layer for "
                      f"'[cyan]{query}[/cyan]'.[/dim]\n")
        return

    console.print(f"\n  [bold]Cross-layer search:[/bold] '[cyan]{query}[/cyan]'\n")

    if scratch:
        console.print(f"  [bold]Scratchpad[/bold]  [dim]({len(scratch)})[/dim]")
        for f in scratch:
            pin = " [yellow]*[/yellow]" if f.get("pinned") else ""
            console.print(f"    [cyan]{f['id']}[/cyan]{pin}  {f['fact'][:80]}")
        console.print()

    if episodic:
        console.print(f"  [bold]Episodic[/bold]  [dim]({len(episodic)})[/dim]")
        for d in episodic:
            console.print(f"    [cyan]{d.short_ref}[/cyan]  {d.content[:80]}")
            console.print(f"        [dim]why:[/dim] {(d.why or '')[:80]}")
        console.print()

    if work:
        console.print(f"  [bold]Working[/bold]  [dim]({len(work)})[/dim]")
        for w in work:
            console.print(f"    [cyan]{w['id']}[/cyan]  {w['note'][:80]}")
        console.print()


@app.command(name="tag-search")
def tag_search(
    prefix: str = typer.Argument(..., help="Tag prefix to match"),
    limit: int = typer.Option(30, "--limit", "-n", help="Max matches"),
) -> None:
    """Find tags by prefix (case-insensitive), with fact counts.

    Useful when you remember "I tagged it 'postg-something'" but not the
    full spelling. Sorted by frequency, most-used first.

    Examples:
      anamne tag-search post   # finds postgres, postgresql, posting
      anamne tag-search py
    """
    from collections import Counter
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    counter: Counter = Counter()
    p_lower = prefix.lower()
    for f in store.list_facts(limit=10_000):
        for t in (f.get("tags") or []):
            if t.lower().startswith(p_lower):
                counter[t] += 1
    if not counter:
        console.print(f"\n  [dim]No tags starting with '[cyan]{prefix}[/cyan]'.[/dim]\n")
        return
    items = counter.most_common(limit)
    console.print(f"\n  [bold]{len(items)} tag(s) starting with '[cyan]{prefix}[/cyan]':[/bold]\n")
    for name, cnt in items:
        console.print(f"  [cyan]{name:30}[/cyan]  [dim]{cnt}[/dim]")
    console.print()


@app.command()
def tail(
    interval: int = typer.Option(5, "--interval", "-i",
                                 help="Poll interval in seconds (min 1)"),
    once: bool = typer.Option(False, "--once", help="Print snapshot and exit"),
) -> None:
    """Live-tail recent memory activity (Ctrl-C to stop).

    Polls the SQLite database every `--interval` seconds and prints any new
    fact creations, retrievals, history events, and working notes since the
    last tick. Useful while doing something else in parallel - the AI assistant
    adds facts in the background and you can watch them land.

    Examples:
      anamne tail                # poll every 5 seconds
      anamne tail --interval 1   # snappier (more CPU)
      anamne tail --once         # one snapshot, no loop
    """
    import sqlite3
    import time
    from datetime import datetime, timezone, timedelta
    from anamne.store.graph import DecisionStore

    if interval < 1:
        interval = 1

    store = DecisionStore()
    db = store._db
    cursor_ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    console.print(f"\n  [bold]anamne tail[/bold]  [dim](Ctrl-C to stop, "
                  f"interval {interval}s)[/dim]\n")

    try:
        while True:
            new_cursor = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(db) as con:
                facts_new = con.execute(
                    "SELECT id, fact, created_at FROM scratchpad "
                    "WHERE created_at > ? ORDER BY created_at ASC",
                    (cursor_ts,),
                ).fetchall()
                try:
                    retr_new = con.execute(
                        "SELECT fact_id, retrieved_at FROM retrieval_log "
                        "WHERE retrieved_at > ? ORDER BY retrieved_at ASC",
                        (cursor_ts,),
                    ).fetchall()
                except Exception:
                    retr_new = []
                try:
                    hist_new = con.execute(
                        "SELECT fact_id, change_type, changed_at FROM fact_history "
                        "WHERE changed_at > ? ORDER BY changed_at ASC",
                        (cursor_ts,),
                    ).fetchall()
                except Exception:
                    hist_new = []
                work_new = con.execute(
                    "SELECT id, note, created_at FROM working_memory "
                    "WHERE created_at > ? ORDER BY created_at ASC",
                    (cursor_ts,),
                ).fetchall()

            for fid, fact, created in facts_new:
                console.print(
                    f"  [dim]{created[:19]}[/dim]  [green]+fact[/green]  "
                    f"[cyan]{fid}[/cyan]  {fact[:70]}"
                )
            for fid, at in retr_new:
                console.print(
                    f"  [dim]{at[:19]}[/dim]  [cyan]~retr[/cyan]   "
                    f"[cyan]{fid}[/cyan]"
                )
            for fid, ct, at in hist_new:
                console.print(
                    f"  [dim]{at[:19]}[/dim]  [yellow]!hist[/yellow]   "
                    f"[cyan]{fid}[/cyan]  ({ct})"
                )
            for wid, note, created in work_new:
                console.print(
                    f"  [dim]{created[:19]}[/dim]  [magenta]+work[/magenta]  "
                    f"[cyan]{wid}[/cyan]  {note[:70]}"
                )

            cursor_ts = new_cursor
            if once:
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n  [dim]stopped[/dim]\n")


@app.command()
def shell() -> None:
    """Interactive REPL for ANAMNE - run commands without re-launching the CLI.

    Built-in commands inside the shell:
      search <query>        - hybrid scratchpad search
      similar <text>        - pure-semantic search
      remember <text>       - store a durable fact
      journal <text>        - timestamped journal entry
      working <text>        - add a working-memory note
      ask <question>        - cross-layer recall (needs API key)
      info <id>             - full details of a fact
      history <id>          - change log for a fact
      recent [N]            - latest N facts (default 10)
      tags                  - list all tags with counts
      status                - quick stats summary
      help                  - show this help
      exit | quit | Ctrl-D  - leave the shell

    Tab completion is enabled on the command name (e.g. `re<TAB>` -> remember).

    Examples:
      anamne shell
    """
    from anamne.store.graph import DecisionStore

    store = DecisionStore()
    COMMANDS = (
        "search", "similar", "remember", "journal", "working", "ask",
        "info", "history", "recent", "tags", "status", "help", "exit", "quit",
    )

    # Best-effort tab completion via stdlib readline.  Skips silently on
    # Windows when pyreadline is not installed - the REPL still works.
    try:
        import readline

        def _completer(prefix: str, state: int):
            matches = [c for c in COMMANDS if c.startswith(prefix)]
            return matches[state] if state < len(matches) else None

        readline.set_completer(_completer)
        readline.parse_and_bind("tab: complete")
    except Exception:
        pass

    console.print()
    console.print("[bold cyan]ANAMNE shell[/bold cyan]  [dim](type 'help' or 'exit')[/dim]")
    console.print()

    def _print_help() -> None:
        console.print(
            "  [bold]Commands:[/bold] search, similar, remember, journal, working, "
            "ask, info, history, recent, tags, status, help, exit"
        )

    while True:
        try:
            line = input("anamne> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return

        if not line:
            continue
        if line in {"exit", "quit", ":q"}:
            console.print("[dim]bye[/dim]")
            return
        if line == "help":
            _print_help()
            continue

        parts = line.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "search" and arg:
                results = store.search_facts_ranked(arg, limit=10)
                if not results:
                    console.print("  [dim]no matches[/dim]")
                for f in results:
                    pin = " [yellow]*[/yellow]" if f.get("pinned") else ""
                    console.print(f"  [cyan]{f['id']}[/cyan]{pin}  {f['fact'][:90]}")
            elif cmd == "similar" and arg:
                results = store.search_facts_semantic(arg, limit=10)
                if not results:
                    console.print("  [dim]no matches[/dim]")
                for f in results:
                    console.print(f"  [cyan]{f['id']}[/cyan]  {f['fact'][:90]}")
            elif cmd == "remember" and arg:
                mid = store.remember(arg)
                console.print(f"  [green]saved[/green] [cyan]{mid}[/cyan]")
            elif cmd == "journal" and arg:
                mid = store.remember(arg, tags=["journal"])
                console.print(f"  [green]journal[/green] [cyan]{mid}[/cyan]")
            elif cmd == "working" and arg:
                wid = store.working_add(arg)
                console.print(f"  [green]working[/green] [cyan]{wid}[/cyan]")
            elif cmd == "ask" and arg:
                try:
                    from anamne.agents.oracle import OracleAgent
                    from anamne.llm import LLMClient
                    agent = OracleAgent(store=store, llm=LLMClient())
                    answer = agent.ask(arg)
                    console.print(answer)
                except Exception as e:
                    console.print(f"  [red]ask failed:[/red] {e}")
            elif cmd == "info" and arg:
                fact = store.get_fact(arg)
                if not fact:
                    console.print("  [red]not found[/red]")
                else:
                    console.print(f"  [cyan]{fact['id']}[/cyan]  {fact['fact']}")
                    console.print(f"  tags: {', '.join(fact['tags']) or '-'}")
                    console.print(f"  created: {fact['created_at']}  "
                                  f"pinned: {fact.get('pinned')}")
            elif cmd == "history" and arg:
                hist = store.get_fact_history(arg)
                if not hist:
                    console.print("  [dim]no history[/dim]")
                for h in hist[-10:]:
                    console.print(
                        f"  [dim]{h['changed_at'][:19]}[/dim]  "
                        f"{h['change_type']:18}  {(h.get('content') or '')[:60]}"
                    )
            elif cmd == "recent":
                n = int(arg) if arg.isdigit() else 10
                import sqlite3
                with sqlite3.connect(store._db) as con:
                    rows = con.execute(
                        "SELECT id, fact, created_at FROM scratchpad "
                        "ORDER BY created_at DESC LIMIT ?", (n,),
                    ).fetchall()
                for fid, fact, created in rows:
                    console.print(
                        f"  [dim]{created[:10]}[/dim]  [cyan]{fid}[/cyan]  {fact[:80]}"
                    )
            elif cmd == "tags":
                from collections import Counter
                counter: Counter = Counter()
                for f in store.list_facts(limit=10_000):
                    for t in (f.get("tags") or []):
                        counter[t] += 1
                if not counter:
                    console.print("  [dim]no tags[/dim]")
                for t, n in counter.most_common(30):
                    console.print(f"  [cyan]{t:30}[/cyan]  {n}")
            elif cmd == "status":
                facts = store.fact_count()
                eps = store.count()
                work = len(store.working_active())
                console.print(
                    f"  scratchpad: [bold]{facts}[/bold]   "
                    f"episodic: [bold]{eps}[/bold]   "
                    f"working: [bold]{work}[/bold]"
                )
            else:
                console.print(
                    "  [yellow]unknown or missing argument.[/yellow]  "
                    "type [bold]help[/bold]"
                )
        except Exception as e:
            console.print(f"  [red]error:[/red] {e}")


@app.command()
def ui(
    port: int = typer.Option(8765, "--port", "-p", help="Local port to listen on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
) -> None:
    """Launch the local web dashboard  - browse all memories in your browser.

    Opens http://127.0.0.1:<port> automatically (pass --no-browser to disable).
    Read-only view: scratchpad facts, search, working memory, indexed repos.
    Press Ctrl+C to stop.

    Example:
      anamne ui
      anamne ui --port 9000 --no-browser
    """
    from anamne.ui.server import run_ui
    run_ui(port=port, open_browser=not no_browser)


# Register mcp-server as an alias so both "mcp" and "mcp-server" work
app.command(name="mcp", hidden=True)(mcp_server)


if __name__ == "__main__":
    app()
