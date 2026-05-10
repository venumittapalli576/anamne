"""
Historian Agent — reads git history and extracts architectural decisions.

For each commit it asks Claude: "what decision was made here and WHY?"
Trivial commits (typos, formatting, bumps) are skipped automatically.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import git
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from anamne.config import get_settings
from anamne.llm import LLMClient
from anamne.models import Decision
from anamne.store.graph import DecisionStore

console = Console()

def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers some models add."""
    s = text.strip()
    if s.startswith("```"):
        # drop the opening fence line and trailing fence
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


# Commit messages that almost never contain architectural decisions
_TRIVIAL = re.compile(
    r"^(merge|revert merge|bump version|update deps?|"
    r"fix typo|fmt|format|lint|whitespace|"
    r"wip|tmp|temp|initial commit|add \.gitignore|"
    r"chore:|style:|docs?:|ci:)",
    re.IGNORECASE,
)

_EXTRACT_PROMPT = """\
Analyze this git commit and extract any ARCHITECTURAL DECISIONS — choices that reflect \
WHY the codebase was built or changed a certain way.

Focus on the reasoning, not the mechanics. Examples of good decisions:
- "Switched from REST to GraphQL because mobile clients need flexible queries"
- "Added Redis caching layer because DB reads were timing out under load"
- "Extracted auth logic into middleware to enable reuse across services"

Commit details:
Hash    : {hash}
Author  : {author}
Date    : {date}
Message :
{message}

Changed files: {files}

Return a JSON array. Return [] if no architectural decision exists (typos, formatting, \
trivial refactors don't count).

Schema:
[
  {{
    "content": "one sentence — what decision was made",
    "why":     "the reasoning / motivation behind it",
    "keywords": ["relevant", "technical", "terms"],
    "confidence": 0.0
  }}
]

Return ONLY valid JSON. No markdown fences, no explanation."""


class HistorianAgent:
    def __init__(self, store: Optional[DecisionStore] = None):
        self._cfg = get_settings()
        self._store = store or DecisionStore()
        self._llm = LLMClient(self._cfg)  # raises with clear msg if no key
        self._model = self._llm.model

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def index_repo(
        self,
        repo_path: str,
        max_commits: int = 500,
        incremental: bool = False,
    ) -> int:
        """Index a git repository. Returns number of decisions stored.

        When incremental=True, only commits not yet in indexed_commits are
        processed. This is used by `anamne sync` to avoid redundant LLM calls.
        """
        path = Path(repo_path).resolve()
        repo_str = str(path)

        try:
            repo = git.Repo(path, search_parent_directories=True)
        except git.InvalidGitRepositoryError:
            console.print(f"[red]Not a git repository:[/red] {path}")
            return 0

        commits = list(repo.iter_commits("HEAD", max_count=max_commits))
        if not commits:
            console.print("[yellow]No commits found.[/yellow]")
            return 0

        if incremental:
            new_commits = [
                c for c in commits
                if not self._store.is_commit_indexed(repo_str, c.hexsha)
            ]
            if not new_commits:
                console.print("[green]Already up to date.[/green] No new commits to index.")
                return 0
            console.print(
                f"[dim]Found [bold]{len(new_commits)}[/bold] new commit(s) "
                f"(of {len(commits)} total) — extracting decisions...[/dim]\n"
            )
            commits = new_commits
        else:
            console.print(
                f"[dim]Found [bold]{len(commits)}[/bold] commits — "
                f"filtering and extracting decisions...[/dim]\n"
            )

        total_indexed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[cyan]{task.completed}[/cyan]/[dim]{task.total}[/dim]"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as prog:
            task = prog.add_task("Analyzing commits", total=len(commits))

            for commit in commits:
                decisions = self._process_commit(commit, repo_str)
                if decisions:
                    self._store.add_many(decisions, repo_path=repo_str)
                    total_indexed += len(decisions)
                # Always mark commit as indexed regardless of whether a decision was found
                self._store.mark_commit_indexed(repo_str, commit.hexsha)
                prog.advance(task)

        return total_indexed

    def index_adr_dir(self, adr_dir: str, repo_path: str = "") -> int:
        """Index Architecture Decision Records (markdown files)."""
        path = Path(adr_dir)
        if not path.exists():
            return 0

        md_files = list(path.glob("*.md")) + list(path.glob("*.MD"))
        indexed = 0

        for md_file in md_files:
            decisions = self._extract_from_adr(md_file)
            self._store.add_many(decisions, repo_path=repo_path)
            indexed += len(decisions)

        return indexed

    # ------------------------------------------------------------------ #
    # Internal                                                              #
    # ------------------------------------------------------------------ #

    def _process_commit(self, commit: git.Commit, repo_path: str) -> list[Decision]:
        message = commit.message.strip()

        if _TRIVIAL.match(message) and len(message) < 60:
            return []
        if len(message) < 20:
            return []

        parent = commit.parents[0] if commit.parents else git.NULL_TREE
        try:
            diff = commit.diff(parent)
            changed_files = [d.a_path or d.b_path for d in diff][:15]
        except Exception:
            changed_files = []

        prompt = _EXTRACT_PROMPT.format(
            hash=commit.hexsha[:8],
            author=commit.author.name,
            date=datetime.fromtimestamp(commit.committed_date, tz=timezone.utc).strftime("%Y-%m-%d"),
            message=message[:2500],
            files=", ".join(changed_files) or "(unknown)",
        )
        try:
            raw = self._llm.complete(prompt, max_tokens=1024).text.strip()
            raw = _strip_code_fence(raw)
            extracted: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            console.log(f"[dim]Skipped {commit.hexsha[:8]} (parse error: {e})[/dim]")
            return []
        except Exception as e:
            # Surface API errors so users see what's wrong instead of silent skips
            console.log(f"[red]LLM call failed on {commit.hexsha[:8]}: {type(e).__name__}: {e}[/red]")
            return []

        decisions = []
        for item in extracted:
            if not item.get("content") or not item.get("why"):
                continue
            decisions.append(
                Decision(
                    content=item["content"],
                    why=item["why"],
                    source_type="commit",
                    source_ref=commit.hexsha,
                    source_author=commit.author.name,
                    file_paths=changed_files,
                    keywords=item.get("keywords", []),
                    created_at=datetime.fromtimestamp(
                        commit.committed_date, tz=timezone.utc
                    ),
                    confidence=float(item.get("confidence", 0.8)),
                )
            )

        return decisions

    def _extract_from_adr(self, md_file: Path) -> list[Decision]:
        """Extract decisions from an ADR markdown file via Claude."""
        text = md_file.read_text(encoding="utf-8", errors="ignore")[:4000]

        prompt = (
            f"Extract architectural decisions from this ADR file.\n\n"
            f"Filename: {md_file.name}\n\nContent:\n{text}\n\n"
            "Return JSON array same schema as before: "
            '[{"content":"...","why":"...","keywords":[],"confidence":0.9}]'
            "\nReturn [] if nothing useful. ONLY JSON."
        )

        try:
            raw = self._llm.complete(prompt, max_tokens=1024).text.strip()
            raw = _strip_code_fence(raw)
            extracted = json.loads(raw)
        except Exception:
            return []

        return [
            Decision(
                content=item["content"],
                why=item["why"],
                source_type="adr",
                source_ref=md_file.name,
                source_author="ADR",
                keywords=item.get("keywords", []),
                confidence=float(item.get("confidence", 0.9)),
            )
            for item in extracted
            if item.get("content") and item.get("why")
        ]
