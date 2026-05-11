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
  facts             - list all scratchpad facts (supports --tag filter)
  journal           - timestamped journal entry
  import-chat       - extract facts from exported AI conversations
  capture-clipboard - save clipboard text as a fact
  consolidate       - merge redundant facts with LLM
  export            - backup all memories to JSON or Markdown

Working memory (session-scoped):
  working           - add/list/clear short-lived context notes

Maintenance:
  clear             - wipe an entire memory layer (scratchpad|working|episodic|all)
  watch             - auto-consolidation daemon (runs periodically)

Server:
  mcp               - start MCP server for Cursor / Claude Code
  mcp-server        - alias for mcp
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    name="anamne",
    help="[bold green]ANAMNE[/bold green] - Brain-inspired personal memory layer for AI tools.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

_BANNER = """[bold green]
╔═══════════════════════════════════════╗
║   A N A M N E   v0.3.0               ║
║   Brain-inspired personal memory      ║
║   layer for AI tools.                 ║
╚═══════════════════════════════════════╝[/bold green]"""


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
    """Incrementally re-index a repository — only processes new commits.

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
        f"[bold green]Watch mode[/bold green] — "
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
                    f"{len(merges)} — {store.fact_count()} remain[/dim]"
                )
            else:
                console.print(f"[dim][run {run}] {fact_count} facts — nothing to merge[/dim]")
        else:
            console.print(
                f"[dim][run {run}] Only {fact_count} fact(s) — "
                f"need {min_cluster}+ to consolidate[/dim]"
            )

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Watch stopped.[/dim]")
            break


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your WHY question about the codebase"),
) -> None:
    """Ask a question — recalls across all three memory layers with citations."""
    _require_api_key()
    from anamne.agents.oracle import OracleAgent

    agent = OracleAgent()
    agent.ask_pretty(question)


# ------------------------------------------------------------------ #
# Memory layer commands (v0.2 — brain-inspired)                        #
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
) -> None:
    """Store a fact in scratchpad memory.

    Short text -> stored verbatim.
    Long text + --distill -> LLM extracts multiple structured facts.
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
            mem_id = store.remember(f.strip(), tags=tag or None)
            console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]: {f}")
        console.print(f"\n[dim]Stored {len(extracted)} fact(s) from input.[/dim]")
    else:
        mem_id = store.remember(fact, tags=tag or None)
        console.print(f"[green]Remembered[/green] [dim]({mem_id})[/dim]: {fact}")
        if tag:
            console.print(f"[dim]  tags: {', '.join(tag)}[/dim]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="What to recall from memory"),
) -> None:
    """Recall across episodic memory and scratchpad facts."""
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    # Scratchpad — ACT-R ranked, no LLM call needed
    facts = store.search_facts_ranked(query, limit=5)
    if facts:
        console.print("\n[bold cyan]From scratchpad:[/bold cyan]")
        for f in facts:
            tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
            console.print(f"  - {f['fact']}{tag_str}")

    # Episodic memory — uses Oracle agent
    if store.count() > 0:
        _require_api_key()
        from anamne.agents.oracle import OracleAgent
        console.print("\n[bold cyan]From episodic memory:[/bold cyan]")
        agent = OracleAgent(store=store)
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
        f"[green]Updated[/green] [cyan]{memory_id}[/cyan] — "
        f"tags: {', '.join(new_tags) if new_tags else '(none)'}"
    )


@app.command()
def consolidate(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview merges without writing anything"
    ),
    threshold: float = typer.Option(
        0.6, "--threshold", "-t",
        help="Jaccard similarity threshold for grouping facts (0–1)"
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
        console.print("[dim]Scratchpad is empty — nothing to consolidate.[/dim]")
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

    mode_label = "[yellow]DRY RUN[/yellow] — " if dry_run else ""
    console.print(f"{mode_label}[bold]{len(merges)} merge(s):[/bold]\n")

    for i, m in enumerate(merges, 1):
        console.print(f"[cyan]Merge {i}:[/cyan]")
        for fact in m["replaced_facts"]:
            console.print(f"  [dim]- {fact}[/dim]")
        console.print(f"  [green]-> {m['merged']}[/green]\n")

    if dry_run:
        console.print(
            "[yellow]Dry run — nothing changed.[/yellow] "
            "Re-run without --dry-run to apply."
        )
    else:
        replaced = sum(len(m["replaced"]) for m in merges)
        console.print(
            f"[green]Done.[/green] Replaced {replaced} facts with {len(merges)} merged fact(s)."
        )


@app.command()
def facts(
    limit: int = typer.Option(20, "--limit", "-n", help="How many to list"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag (repeatable)"),
) -> None:
    """List facts in scratchpad memory, optionally filtered by tag."""
    from anamne.store.graph import DecisionStore
    store = DecisionStore()
    rows = store.list_facts(limit=limit, tags=tag or None)
    if not rows:
        if tag:
            console.print(f"[dim]No facts tagged: {', '.join(tag)}[/dim]")
        else:
            console.print("[dim]Scratchpad is empty. Try [bold]anamne remember \"...\"[/bold][/dim]")
        return
    for f in rows:
        tag_str = f"  [dim]({', '.join(f['tags'])})[/dim]" if f['tags'] else ""
        console.print(f"[cyan]{f['id']}[/cyan]  {f['fact']}{tag_str}")


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
      anamne journal "Finally fixed the Stripe webhook double-fire — idempotency key was wrong"
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
        "that are worth keeping long-term — things that will still be useful "
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
        console.print(f"\n[yellow]Dry run — nothing stored.[/yellow] Remove --dry-run to save.")
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


def _parse_chat_json(raw: str, source: str) -> str:
    """Try to extract human-readable conversation text from a JSON export."""
    import json as _json

    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        # Not valid JSON — treat as text
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

    # Unknown structure — just dump readable content
    else:
        return _json.dumps(data, indent=2)[:12000]

    return "\n".join(lines)[:12000]


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Filter by tag (repeatable)"),
    no_rank: bool = typer.Option(
        False, "--no-rank", help="Skip ACT-R ranking, use raw recency order"
    ),
) -> None:
    """Search scratchpad facts directly — no LLM, no API key required.

    Results are ranked by ACT-R activation (recency + frequency of use)
    so the most relevant facts surface first. Uses hybrid search (substring
    + semantic embeddings) by default. Use --no-rank for raw recency order.

    Examples:
      anamne search postgres
      anamne search "python preference" --limit 5
      anamne search auth --tag security
    """
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if no_rank:
        results = store.search_facts(query, limit=limit, tags=tag or None)
    else:
        # Get ranked results then apply tag filter
        results = store.search_facts_ranked(query, limit=limit * 2)
        if tag:
            tag_set = set(tag)
            results = [f for f in results if tag_set.intersection(f.get("tags", []))]
        results = results[:limit]

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
        console.print(f"  [cyan]{f['id']}[/cyan]  {f['fact']}{tag_str}")
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
) -> None:
    """Export all memories to JSON or Markdown for backup or migration.

    Examples:
      anamne export --output backup.json
      anamne export --format markdown --output memories.md
      anamne export --no-episodic --output facts-only.json
    """
    import json as _json
    from datetime import date
    from anamne.store.graph import DecisionStore

    store = DecisionStore()

    if fmt == "markdown":
        lines: list[str] = [
            f"# ANAMNE Memory Export",
            f"*Exported {date.today().isoformat()}*\n",
        ]

        if not no_facts:
            facts = store.list_facts(limit=10_000)
            lines.append(f"## Scratchpad Facts ({len(facts)})\n")
            for f in facts:
                tag_str = f" _{', '.join(f['tags'])}_" if f.get("tags") else ""
                lines.append(f"- **{f['id']}**: {f['fact']}{tag_str}")
            lines.append("")

        if not no_working:
            working_items = store.working_active()
            lines.append(f"## Working Memory ({len(working_items)} active)\n")
            for w in working_items:
                lines.append(f"- {w['note']} *(expires {w['expires_at']})*")
            lines.append("")

        if not no_episodic:
            decisions = store.list_all_decisions(limit=10_000)
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

        if not no_facts:
            payload["scratchpad_facts"] = store.list_facts(limit=10_000)

        if not no_working:
            payload["working_memory"] = store.working_active()

        if not no_episodic:
            payload["episodic_decisions"] = [
                d.to_dict() for d in store.list_all_decisions(limit=10_000)
            ]

        content = _json.dumps(payload, indent=2, default=str)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Exported[/green] to [bold]{output}[/bold]")
    else:
        console.print(content)


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

    Useful for quickly capturing something interesting you've copied — a quote,
    a decision, a snippet of context — without switching to another app.

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
        console.print("[yellow]Dry run — nothing stored.[/yellow]")
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
) -> None:
    """Manage working memory (short-lived session context)."""
    from anamne.store.graph import DecisionStore
    store = DecisionStore()

    if clear:
        n = store.working_clear()
        console.print(f"[green]Cleared[/green] {n} working memory items")
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
      scratchpad  — all durable facts and their ACT-R retrieval history
      working     — all active working-memory notes
      episodic    — all indexed decisions and commit history
      all         — everything above

    Examples:
      anamne clear working               # wipe session notes
      anamne clear scratchpad --yes      # skip confirmation
    """
    valid = {"scratchpad", "working", "episodic", "all"}
    if layer not in valid:
        console.print(
            f"[red]Unknown layer: {layer}[/red] — choose from: {', '.join(sorted(valid))}"
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
        else "[yellow]empty — run: anamne index . or anamne remember ...[/yellow]",
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

    console.print()
    console.print(table)
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
        # Stderr-only — must not pollute stdout
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


# Register mcp-server as an alias so both "mcp" and "mcp-server" work
app.command(name="mcp", hidden=True)(mcp_server)


if __name__ == "__main__":
    app()
