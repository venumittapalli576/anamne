"""
PROVENANCE CLI - The living memory of why your code exists.

Commands:
  init    - set up PROVENANCE for a project
  index   - read git history and build the knowledge graph
  ask     - ask why something exists (the main demo)
  status  - show knowledge base stats
  mcp     - start the MCP server for Cursor / Claude Code
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
    name="provenance",
    help="[bold green]PROVENANCE[/bold green] - The living memory of [italic]why[/italic] your code exists.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

_BANNER = """[bold green]
╔═══════════════════════════════════════╗
║   P R O V E N A N C E   v0.1.0       ║
║   The living memory of why your       ║
║   code exists.                        ║
╚═══════════════════════════════════════╝[/bold green]"""


def _require_api_key() -> None:
    from provenance.config import get_settings
    cfg = get_settings()
    has_claude = bool(cfg.anthropic_api_key and cfg.anthropic_api_key != "your-key-here")
    has_gemini = bool(cfg.gemini_api_key)
    if not (has_claude or has_gemini):
        console.print(
            "\n[red bold]No LLM API key configured.[/red bold]\n"
            "  Quickest fix: run [bold]provenance init[/bold]\n"
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

    from provenance.config import get_settings
    cfg = get_settings()
    repo_path = (repo or Path.cwd()).resolve()

    # 1. Detect current model situation
    console.print("\n[bold]Step 1/3 - Detecting available LLM[/bold]")
    if cfg.anthropic_api_key:
        console.print("[green]Found[/green] Anthropic key - will use [cyan]Claude Sonnet 4.6[/cyan] (best quality)")
    elif cfg.gemini_api_key:
        console.print("[green]Found[/green] Gemini key - will use [cyan]Gemini 2.5 Flash[/cyan] (free tier)")
    else:
        console.print("[yellow]No API key found.[/yellow] Three options:\n")
        console.print("  [bold]1[/bold]  Gemini 2.5 Flash  [green](free tier - recommended)[/green]")
        console.print("     -> Sign in at [link]https://aistudio.google.com/apikey[/link]")
        console.print("  [bold]2[/bold]  Claude Sonnet 4.6  [dim](best quality, paid)[/dim]")
        console.print("     -> Get a key at [link]https://platform.anthropic.com[/link]")
        console.print("  [bold]3[/bold]  Ollama (llama3.2)  [dim](free, offline, ~4GB disk, slower)[/dim]")
        console.print("     -> Install from [link]https://ollama.com[/link]\n")
        choice = typer.prompt("Pick 1, 2, or 3", default="1").strip()
        chosen = {"1": "gemini", "2": "claude", "3": "ollama"}.get(choice, "gemini")

        env_file = Path(".env")
        existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

        if chosen == "claude":
            key = typer.prompt("Paste your Anthropic API key (starts with sk-ant-)", hide_input=True)
            existing += f"\nANTHROPIC_API_KEY={key.strip()}\n"
        elif chosen == "gemini":
            key = typer.prompt("Paste your Gemini API key", hide_input=True)
            existing += f"\nGEMINI_API_KEY={key.strip()}\n"
        else:
            existing += "\nMODEL=ollama/llama3.2\n"
            console.print(
                "[yellow]Note:[/yellow] make sure Ollama is running and "
                "[cyan]ollama pull llama3.2[/cyan] has completed."
            )

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
        console.print(f"\nRun [bold]provenance index {repo_path}[/bold] when ready.")
        return

    is_git_repo = (repo_path / ".git").exists()
    if not is_git_repo:
        console.print(f"[yellow]Note:[/yellow] [cyan]{repo_path}[/cyan] is not a git repo. Skipping auto-index.")
        console.print("\nRun [bold]provenance index <path-to-repo>[/bold] later.")
        return

    if typer.confirm(f"Index {repo_path} now?", default=True):
        from provenance.agents.historian import HistorianAgent
        from provenance.store.graph import DecisionStore

        store = DecisionStore()
        agent = HistorianAgent(store=store)
        count = agent.index_repo(str(repo_path), max_commits=200)
        console.print(f"\n[bold green]Done[/bold green] - indexed {count} decisions.")

        if count > 0:
            console.print(
                '\nTry it now:\n'
                '  [bold]provenance ask "what was this project built for?"[/bold]'
            )
        else:
            console.print(
                "[yellow]No decisions extracted.[/yellow] "
                "Likely the commit messages are too short or trivial."
            )
    else:
        console.print(f"\nRun [bold]provenance index {repo_path}[/bold] when ready.")


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

    from provenance.agents.historian import HistorianAgent
    from provenance.store.graph import DecisionStore

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
        console.print('Try: [bold]provenance ask "why does X exist?"[/bold]')
    else:
        console.print(
            "[yellow]No decisions extracted.[/yellow] "
            "Commits may be too short or trivial."
        )


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your WHY question about the codebase"),
) -> None:
    """Ask the Oracle why something was built a certain way."""
    _require_api_key()
    from provenance.agents.oracle import OracleAgent

    agent = OracleAgent()
    agent.ask_pretty(question)


@app.command()
def status() -> None:
    """Show knowledge base stats."""
    from provenance.config import get_settings
    from provenance.store.graph import DecisionStore

    cfg = get_settings()
    store = DecisionStore()
    count = store.count()
    repos = store.all_repos()

    table = Table(
        title="PROVENANCE Status",
        border_style="green",
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("Decisions indexed", f"[bold]{count}[/bold]")
    table.add_row(
        "Status",
        "[green]ready[/green]" if count > 0 else "[yellow]empty - run: provenance index .[/yellow]",
    )
    table.add_row("Indexed repos", str(len(repos)) if repos else "none")
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Model", cfg.resolved_model() or "[dim](not set)[/dim]")
    table.add_row(
        "Tier",
        cfg.model_tier(),
    )
    table.add_row(
        "API key",
        "[green]set[/green]"
        if cfg.anthropic_api_key and cfg.anthropic_api_key != "your-key-here"
        else "[red]missing[/red]",
    )

    if repos:
        table.add_row("Repos", "\n".join(repos))

    console.print()
    console.print(table)
    console.print()


@app.command()
def mcp_server() -> None:
    """Start the MCP server - connects PROVENANCE to Cursor / Claude Code."""
    _require_api_key()
    from provenance.mcp.server import run

    console.print(
        Panel(
            "[bold]Starting PROVENANCE MCP server[/bold]\n\n"
            "Add to [bold]Claude Code[/bold] (.claude/settings.json):\n"
            '[cyan]{ "mcpServers": { "provenance": { "command": "provenance", "args": ["mcp-server"] } } }[/cyan]\n\n'
            "Add to [bold]Cursor[/bold] (Settings -> MCP):\n"
            '[cyan]{ "command": "provenance mcp-server" }[/cyan]',
            border_style="green",
        )
    )
    run()


# Register mcp-server as an alias so both "mcp" and "mcp-server" work
app.command(name="mcp", hidden=True)(mcp_server)


if __name__ == "__main__":
    app()
