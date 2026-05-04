"""
PROVENANCE CLI — The living memory of why your code exists.

Commands:
  init    — set up PROVENANCE for a project
  index   — read git history and build the knowledge graph
  ask     — ask why something exists (the main demo)
  status  — show knowledge base stats
  mcp     — start the MCP server for Cursor / Claude Code
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
    help="[bold green]PROVENANCE[/bold green] — The living memory of [italic]why[/italic] your code exists.",
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


def _require_api_key() -> str:
    from provenance.config import get_settings
    cfg = get_settings()
    if not cfg.anthropic_api_key or cfg.anthropic_api_key == "your-key-here":
        console.print(
            "\n[red bold]✗ ANTHROPIC_API_KEY not set.[/red bold]\n"
            "  1. Create a [bold].env[/bold] file in this directory\n"
            "  2. Add: [cyan]ANTHROPIC_API_KEY=sk-ant-...[/cyan]\n"
            "  3. Get your key: [link]https://platform.anthropic.com[/link]\n"
        )
        raise typer.Exit(1)
    return cfg.anthropic_api_key


# ------------------------------------------------------------------ #
# Commands                                                             #
# ------------------------------------------------------------------ #

@app.command()
def init(
    repo: Optional[Path] = typer.Argument(
        None, help="Repository path (default: current directory)"
    ),
) -> None:
    """Set up PROVENANCE for a project."""
    console.print(_BANNER)
    repo_path = (repo or Path.cwd()).resolve()

    env_file = Path(".env")
    if not env_file.exists():
        env_file.write_text(
            "# PROVENANCE — add your Claude API key\n"
            "ANTHROPIC_API_KEY=your-key-here\n",
            encoding="utf-8",
        )
        console.print(f"[green]✓ Created[/green] [bold].env[/bold]")
        console.print(
            "  → Open [bold].env[/bold] and paste your key from "
            "[link]https://platform.anthropic.com[/link]\n"
        )
    else:
        console.print("[green]✓[/green] [bold].env[/bold] already exists")

    from provenance.config import get_settings
    cfg = get_settings()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Data directory: [dim]{cfg.data_dir}[/dim]")
    console.print(f"[green]✓[/green] Repository: [cyan]{repo_path}[/cyan]\n")
    console.print("Next step → [bold]provenance index .[/bold]")


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
    """Index a repository — read git history and build the WHY knowledge graph."""
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
        f"\n[bold green]✓ Done![/bold green] "
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
        "[green]ready[/green]" if count > 0 else "[yellow]empty — run: provenance index .[/yellow]",
    )
    table.add_row("Indexed repos", str(len(repos)) if repos else "none")
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Model", cfg.model)
    table.add_row(
        "API key",
        "[green]✓ set[/green]"
        if cfg.anthropic_api_key and cfg.anthropic_api_key != "your-key-here"
        else "[red]✗ missing[/red]",
    )

    if repos:
        table.add_row("Repos", "\n".join(repos))

    console.print()
    console.print(table)
    console.print()


@app.command()
def mcp_server() -> None:
    """Start the MCP server — connects PROVENANCE to Cursor / Claude Code."""
    _require_api_key()
    from provenance.mcp.server import run

    console.print(
        Panel(
            "[bold]Starting PROVENANCE MCP server[/bold]\n\n"
            "Add to [bold]Claude Code[/bold] (.claude/settings.json):\n"
            '[cyan]{ "mcpServers": { "provenance": { "command": "provenance", "args": ["mcp-server"] } } }[/cyan]\n\n'
            "Add to [bold]Cursor[/bold] (Settings → MCP):\n"
            '[cyan]{ "command": "provenance mcp-server" }[/cyan]',
            border_style="green",
        )
    )
    run()


# Register mcp-server as an alias so both "mcp" and "mcp-server" work
app.command(name="mcp", hidden=True)(mcp_server)


if __name__ == "__main__":
    app()
