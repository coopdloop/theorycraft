#!/usr/bin/env python3
"""
scripts/commit.py — interactive conventional commit CLI for theorycraft.

Usage:
    uv run python scripts/commit.py
    uv run python scripts/commit.py --push
    uv run python scripts/commit.py --dry-run
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich import print as rprint

app = typer.Typer(add_completion=False)
console = Console()


# ── Conventional commit config ─────────────────────────────────────────────

COMMIT_TYPES: list[tuple[str, str]] = [
    ("feat",     "A new feature"),
    ("fix",      "A bug fix"),
    ("docs",     "Documentation changes only"),
    ("style",    "Formatting, whitespace — no logic change"),
    ("refactor", "Code restructure without feature or fix"),
    ("perf",     "Performance improvement"),
    ("test",     "Add or fix tests"),
    ("chore",    "Build, deps, tooling, config"),
    ("ci",       "CI/CD pipeline changes"),
    ("revert",   "Revert a previous commit"),
]

TYPE_KEYS = [t[0] for t in COMMIT_TYPES]

MAX_SUBJECT_LEN = 72


# ── Git helpers ────────────────────────────────────────────────────────────

@dataclass
class FileStatus:
    code: str      # XY from git status --porcelain
    path: str
    orig_path: Optional[str] = None  # for renames

    @property
    def display_code(self) -> str:
        return self.code.strip() or "?"

    @property
    def color(self) -> str:
        c = self.display_code
        if "?" in c:   return "dim"
        if "A" in c:   return "green"
        if "D" in c:   return "red"
        if "R" in c:   return "cyan"
        return "yellow"

    @property
    def label(self) -> str:
        c = self.display_code
        if "?" in c:  return "untracked"
        if "A" in c:  return "added"
        if "D" in c:  return "deleted"
        if "R" in c:  return "renamed"
        if "M" in c:  return "modified"
        if "C" in c:  return "copied"
        return c


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _git_status() -> list[FileStatus]:
    result = _run(["git", "status", "--porcelain", "-u"])
    files: list[FileStatus] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        code = line[:2]
        rest = line[3:]
        if " -> " in rest:
            orig, _, new = rest.partition(" -> ")
            files.append(FileStatus(code=code, path=new.strip(), orig_path=orig.strip()))
        else:
            files.append(FileStatus(code=code, path=rest.strip()))
    return files


def _current_branch() -> str:
    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    return r.stdout.strip() or "main"


def _remotes() -> list[str]:
    r = _run(["git", "remote"], check=False)
    return [x for x in r.stdout.strip().splitlines() if x]


def _staged_files() -> list[FileStatus]:
    return [f for f in _git_status() if f.code[0] != " " and f.code[0] != "?"]


# ── UI helpers ─────────────────────────────────────────────────────────────

def _print_header() -> None:
    console.print(Panel(
        "[bold cyan]theorycraft commit[/]  ·  conventional commits",
        expand=False,
        border_style="cyan",
    ))


def _show_status_table(files: list[FileStatus], title: str = "Working tree") -> None:
    if not files:
        console.print(f"[dim]{title}: nothing to show[/]")
        return
    table = Table(title=title, show_header=True, header_style="bold", expand=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("status", width=10)
    table.add_column("file")
    for i, f in enumerate(files, 1):
        label = Text(f.label, style=f.color)
        path = f.path
        if f.orig_path:
            path = f"{f.orig_path} → {f.path}"
        table.add_row(str(i), label, path)
    console.print(table)


def _show_type_table() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column("type", style="bold cyan", width=12)
    table.add_column("description", style="dim")
    for abbrev, desc in COMMIT_TYPES:
        table.add_row(abbrev, desc)
    console.print(Panel(table, title="[bold]commit types[/]", border_style="dim"))


def _pick_files_to_stage(files: list[FileStatus]) -> list[str]:
    """Show file list and let user pick which to stage."""
    _show_status_table(files, "Unstaged / untracked changes")
    console.print()
    console.print("[dim]Enter file numbers to stage (e.g. [bold]1,3,5[/]), [bold]all[/] to stage everything, or [bold]q[/] to quit.[/]")

    while True:
        choice = Prompt.ask("[bold yellow]stage[/]", default="all")

        if choice.lower() == "q":
            raise typer.Exit(0)

        if choice.lower() in {"all", "a", "*"}:
            return [f.path for f in files]

        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            selected = [files[i].path for i in indices if 0 <= i < len(files)]
            if selected:
                return selected
        except (ValueError, IndexError):
            pass

        console.print("[red]Invalid selection — try again.[/]")


def _stage_files(paths: list[str]) -> None:
    _run(["git", "add", "--"] + paths)
    console.print(f"[green]✓[/] Staged [bold]{len(paths)}[/] file(s).")


# ── Commit message builder ─────────────────────────────────────────────────

@dataclass
class ConventionalCommit:
    type: str = ""
    scope: str = ""
    breaking: bool = False
    subject: str = ""
    body: str = ""
    footer: str = ""

    def render(self) -> str:
        scope_part = f"({self.scope})" if self.scope else ""
        bang = "!" if self.breaking else ""
        header = f"{self.type}{scope_part}{bang}: {self.subject}"

        parts = [header]
        if self.body:
            parts.append("")
            parts.append(self.body)
        if self.breaking and self.body:
            # Breaking change footer already implied by ! in header, but add note
            footer_lines = [f"BREAKING CHANGE: {self.body.splitlines()[0]}"]
            if self.footer:
                footer_lines.append(self.footer)
            parts.append("")
            parts.append("\n".join(footer_lines))
        elif self.footer:
            parts.append("")
            parts.append(self.footer)
        return "\n".join(parts)

    def is_valid(self) -> tuple[bool, str]:
        if not self.type:
            return False, "type is required"
        if self.type not in TYPE_KEYS:
            return False, f"type must be one of: {', '.join(TYPE_KEYS)}"
        if not self.subject:
            return False, "subject is required"
        if len(self.subject) > MAX_SUBJECT_LEN:
            return False, f"subject too long ({len(self.subject)} > {MAX_SUBJECT_LEN} chars)"
        if self.subject[0].isupper():
            return False, "subject should start lowercase (e.g. 'add feature', not 'Add feature')"
        if self.subject.endswith("."):
            return False, "subject should not end with a period"
        return True, ""


def _prompt_commit(cc: Optional[ConventionalCommit] = None) -> ConventionalCommit:
    cc = cc or ConventionalCommit()
    console.print()
    _show_type_table()

    cc.type = Prompt.ask(
        "[bold cyan]type[/]",
        choices=TYPE_KEYS,
        default=cc.type or "feat",
    )

    scope_input = Prompt.ask(
        "[bold cyan]scope[/] [dim](optional — module or area, e.g. graph, cli, models)[/]",
        default=cc.scope or "",
    )
    cc.scope = scope_input.strip()

    cc.breaking = Confirm.ask(
        "[bold red]breaking change?[/]",
        default=cc.breaking,
    )

    console.print(f"[dim]Subject: one line, imperative mood, max {MAX_SUBJECT_LEN} chars, lowercase start, no period[/]")
    while True:
        cc.subject = Prompt.ask("[bold cyan]subject[/]", default=cc.subject or "").strip()
        ok, err = ConventionalCommit(type=cc.type, subject=cc.subject).is_valid()
        if cc.subject:
            char_color = "red" if len(cc.subject) > MAX_SUBJECT_LEN else "dim"
            console.print(f"[{char_color}]{len(cc.subject)}/{MAX_SUBJECT_LEN} chars[/]")
        if ok or not cc.subject:
            # re-validate fully
            tmp = ConventionalCommit(type=cc.type, scope=cc.scope, breaking=cc.breaking, subject=cc.subject)
            ok2, err2 = tmp.is_valid()
            if ok2:
                break
            console.print(f"[red]✗[/] {err2}")
        else:
            console.print(f"[red]✗[/] {err}")

    body_input = Prompt.ask(
        "[bold cyan]body[/] [dim](optional — press Enter to skip)[/]",
        default=cc.body or "",
    )
    cc.body = body_input.strip()

    footer_input = Prompt.ask(
        "[bold cyan]footer[/] [dim](optional — e.g. 'Closes #42, Refs #17')[/]",
        default=cc.footer or "",
    )
    cc.footer = footer_input.strip()

    return cc


def _preview_commit(cc: ConventionalCommit) -> None:
    msg = cc.render()
    console.print()
    console.print(Panel(
        f"[bold green]{msg}[/]",
        title="[bold]commit message preview[/]",
        border_style="green",
    ))


# ── Main command ───────────────────────────────────────────────────────────

@app.command()
def main(
    push: bool = typer.Option(False, "--push", "-p", help="Push after committing"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without committing"),
    all_files: bool = typer.Option(False, "--all", "-a", help="Stage all changes without prompting"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (non-interactive)"),
    commit_type: Optional[str] = typer.Option(None, "--type", "-t", help=f"Commit type ({', '.join(TYPE_KEYS)})"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope (optional)"),
    subject: Optional[str] = typer.Option(None, "--subject", "-m", help="Commit subject line"),
    body: Optional[str] = typer.Option(None, "--body", help="Commit body (optional)"),
    footer: Optional[str] = typer.Option(None, "--footer", help="Commit footer, e.g. 'Closes #42'"),
    breaking: bool = typer.Option(False, "--breaking", help="Mark as breaking change"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="Comma-separated file numbers or paths to stage"),
) -> None:
    """Interactive conventional commit CLI. Pass --type and --subject to skip prompts."""
    _print_header()

    # ── Check we're in a git repo ──────────────────────────────────────────
    r = _run(["git", "rev-parse", "--git-dir"], check=False)
    if r.returncode != 0:
        console.print("[red]Not inside a git repository.[/]")
        raise typer.Exit(1)

    branch = _current_branch()
    console.print(f"[dim]Branch:[/] [yellow]{branch}[/]")
    console.print()

    non_interactive = commit_type is not None and subject is not None

    # ── Staging ───────────────────────────────────────────────────────────
    all_changed = _git_status()
    already_staged = _staged_files()
    unstaged = [f for f in all_changed if f not in already_staged]

    if files is not None:
        # Explicit file list: treat entries as paths or 1-based indices into unstaged
        selected: list[str] = []
        for token in files.split(","):
            token = token.strip()
            try:
                idx = int(token) - 1
                if 0 <= idx < len(unstaged):
                    selected.append(unstaged[idx].path)
            except ValueError:
                selected.append(token)
        if selected and not dry_run:
            _stage_files(selected)
        elif selected:
            console.print(f"[dim][dry-run] would stage: {selected}[/]")
    elif all_files and unstaged:
        _stage_files([f.path for f in unstaged])
    elif unstaged and not already_staged:
        if non_interactive:
            console.print("[red]Nothing staged and --files/--all not provided.[/]")
            raise typer.Exit(1)
        paths = _pick_files_to_stage(unstaged)
        if not dry_run:
            _stage_files(paths)
        else:
            console.print(f"[dim][dry-run] would stage: {paths}[/]")
    elif unstaged and already_staged:
        console.print(f"[dim]{len(already_staged)} file(s) already staged. {len(unstaged)} more unstaged:[/]")
        _show_status_table(unstaged, "Also unstaged")
        if not non_interactive and Confirm.ask("Stage remaining files too?", default=False):
            if not dry_run:
                _stage_files([f.path for f in unstaged])

    # ── Verify something is staged ────────────────────────────────────────
    staged_now = _staged_files()
    if not staged_now and not dry_run:
        console.print("[red]Nothing staged — nothing to commit.[/]")
        raise typer.Exit(1)

    if staged_now:
        console.print()
        _show_status_table(staged_now, "Staged for commit")

    # ── Commit message ────────────────────────────────────────────────────
    if non_interactive:
        cc = ConventionalCommit(
            type=commit_type,
            scope=scope or "",
            breaking=breaking,
            subject=subject,
            body=body or "",
            footer=footer or "",
        )
        ok, err = cc.is_valid()
        if not ok:
            console.print(f"[red]✗[/] {err}")
            raise typer.Exit(1)
    else:
        cc = _prompt_commit()

    if non_interactive or yes:
        _preview_commit(cc)
    else:
        while True:
            _preview_commit(cc)
            action = Prompt.ask(
                "[bold]confirm[/]",
                choices=["commit", "edit", "abort"],
                default="commit",
            )
            if action == "commit":
                break
            if action == "edit":
                cc = _prompt_commit(cc)
            if action == "abort":
                console.print("[dim]Aborted.[/]")
                raise typer.Exit(0)

    # ── Commit ────────────────────────────────────────────────────────────
    msg = cc.render()
    if dry_run:
        console.print(f"\n[dim][dry-run] would run: git commit -m {msg!r}[/]")
    else:
        result = _run(["git", "commit", "-m", msg], check=False)
        if result.returncode != 0:
            console.print(f"[red]Commit failed:[/]\n{result.stderr}")
            raise typer.Exit(1)
        hash_r = _run(["git", "rev-parse", "--short", "HEAD"], check=False)
        short = hash_r.stdout.strip()
        console.print(f"\n[green]✓[/] Committed [bold]{short}[/]  [dim]{cc.type}: {cc.subject}[/]")

    # ── Push ──────────────────────────────────────────────────────────────
    remotes = _remotes()

    if not push and not dry_run and not non_interactive and not yes:
        push = Confirm.ask(f"\nPush [yellow]{branch}[/] to remote?", default=False)

    if push:
        remote = "origin"
        if len(remotes) > 1 and not non_interactive and not yes:
            remote = Prompt.ask("Remote", choices=remotes, default="origin")
        elif not remotes:
            console.print("[yellow]No remotes configured — skipping push.[/]")
            return

        cmd = ["git", "push", remote, branch]
        if dry_run:
            console.print(f"[dim][dry-run] would run: {' '.join(cmd)}[/]")
        else:
            console.print(f"[dim]Pushing to [bold]{remote}/{branch}[/]...[/]")
            result = _run(cmd, check=False)
            if result.returncode != 0:
                result2 = _run(["git", "push", "--set-upstream", remote, branch], check=False)
                if result2.returncode != 0:
                    console.print(f"[red]Push failed:[/]\n{result2.stderr}")
                    raise typer.Exit(1)
            console.print(f"[green]✓[/] Pushed to [bold]{remote}/{branch}[/]")


if __name__ == "__main__":
    app()
