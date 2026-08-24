from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from langgraph.types import Command
from rich import print as rprint
from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from theorycraft.creatures import EGG_FRAMES, RARITY_COLOR, select_creature
from theorycraft.llm.router import get_total_tokens, reset_tokens
from theorycraft.utils import DESIGN_NODE_LABELS, DESIGN_NODES

app = typer.Typer(
    name="theorycraft",
    help="Collaborative LangGraph agent that theory-crafts product ideas into product-as-code specs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────

def _print_header(session_name: str, session_id: str) -> None:
    from theorycraft.config import get_settings
    cfg = get_settings()
    lf_status = "[green]enabled[/]" if cfg.langfuse_enabled else "[dim]disabled[/]"
    console.print(
        Panel(
            f"[bold cyan]theorycraft[/]  ·  collaborative product spec builder\n"
            f"[dim]Session:[/] [yellow]{session_name}[/]  [dim]·[/]  "
            f"[dim]Model:[/] [blue]{cfg.model}[/]  [dim]·[/]  "
            f"[dim]Langfuse:[/] {lf_status}",
            expand=False,
        )
    )


def _get_session_db(session_name: str) -> str:
    from theorycraft.config import get_settings
    cfg = get_settings()
    return str(cfg.sessions_dir / f"{session_name}.db")


def _slugify(text: str) -> str:
    from slugify import slugify
    return slugify(text, max_length=40) or "my-product"


def _parse_questions(text: str) -> list[str]:
    """Extract numbered questions from an LLM-generated list."""
    import re
    # Split on lines that start with a number + period/paren
    parts = re.split(r'\n\s*\d+[.)]\s*', text.strip())
    # First part is any preamble before question 1 — drop if empty
    questions = [p.strip() for p in parts if p.strip()]
    # If no numbered structure found, treat the whole text as one question
    return questions if len(questions) > 1 else [text.strip()]


def _multiline_prompt(prompt_prefix: str, hint: str = "") -> str:
    """Collect multiple lines until the user submits a blank line."""
    if hint:
        console.print(f"[dim]{hint}[/]")
    lines: list[str] = []
    while True:
        line = Prompt.ask(prompt_prefix)
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def _handle_interrupt(interrupt_payload: dict) -> str:
    """Render interrupt payload to the terminal and collect user input."""
    interrupt_type = interrupt_payload.get("type", "unknown")

    if interrupt_type == "intake":
        console.print()
        console.print(Panel(
            "[bold]What idea would you like to theorycraft today?[/]\n"
            "[dim]Describe your product idea — be as specific or vague as you like.[/]",
            title="[cyan]intake[/]",
            border_style="cyan",
        ))
        return Prompt.ask("[bold cyan]>[/]")

    elif interrupt_type == "clarify":
        console.print()
        questions_text = interrupt_payload.get("questions", "")
        round_num = interrupt_payload.get("round", 1)
        questions = _parse_questions(questions_text)

        answers: list[str] = []
        for i, question in enumerate(questions, 1):
            console.print()
            console.print(Panel(
                escape(question),
                title=f"[yellow]clarify[/] [dim](round {round_num} · question {i}/{len(questions)})[/]",
                border_style="yellow",
            ))
            answer = Prompt.ask("[bold yellow]>[/]")
            answers.append(f"{i}. {answer}")

        return "\n".join(answers)

    elif interrupt_type == "ideate":
        console.print()
        console.print(Panel(
            escape(interrupt_payload.get("concept", "")),
            title=f"[green]theorycraft[/] [dim](round {interrupt_payload.get('round', 1)})[/]",
            border_style="green",
        ))
        console.print("[dim]Type [bold]/ready[/] to proceed, or share feedback (blank line to submit).[/]")
        _READY = {"/ready", "ready", "/go", "go"}
        lines: list[str] = []
        while True:
            line = Prompt.ask("[bold green]>[/]")
            if line.strip().lower() in _READY:
                return line.strip()
            if line == "" and lines:
                break
            if line:
                lines.append(line)
        return "\n".join(lines)

    elif interrupt_type == "validate":
        console.print()
        summary_lines = interrupt_payload.get("summary", "").split("\n  ")
        tree = Tree("[bold]Spec Preview[/]")
        for line in summary_lines:
            if line.strip():
                tree.add(escape(line.strip()))
        console.print(Panel(tree, title="[magenta]review[/]", border_style="magenta"))
        console.print("[dim]Commands: [bold]approve[/] · [bold]revise <section>: <feedback>[/] · [bold]restart[/][/]")
        return Prompt.ask("[bold magenta]>[/]")

    else:
        console.print(Panel(escape(str(interrupt_payload)), title="[red]interrupt[/]"))
        return Prompt.ask("[bold]>[/]")



class _Progress:
    def __init__(self, max_clarify_rounds: int) -> None:
        # intake + clarify rounds + ideate(est 1) + 7 design nodes + validate + spec_compile
        self.total = 1 + max_clarify_rounds + 1 + 7 + 1 + 1
        self.completed = 0

    def advance(self) -> None:
        self.completed = min(self.completed + 1, self.total)


class _HUDState:
    def __init__(self, progress: _Progress, model: str) -> None:
        self.progress = progress
        self.model = model
        self.creature: Any = None
        self.egg_frame: int = 0
        self.status: str = "starting…"
        self.spinning: bool = True


def _make_hud(hud: _HUDState) -> Panel:
    if hud.creature:
        art = hud.creature.ascii_art
        color = RARITY_COLOR.get(hud.creature.rarity, "white")
        title = f"[bold {color}]{hud.creature.rarity}[/]  ✨  [bold]{hud.creature.name}[/]"
    else:
        art = EGG_FRAMES[hud.egg_frame]
        color = "dim"
        title = "[dim]egg[/]"

    bar_width = 16
    filled = int(bar_width * hud.progress.completed / max(hud.progress.total, 1))
    bar = "█" * filled + "░" * (bar_width - filled)
    tokens = get_total_tokens()
    tok_str = f"{tokens:,} tok" if tokens < 10_000 else f"{tokens / 1000:.1f}k tok"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=18, no_wrap=True)
    grid.add_column()
    grid.add_row(
        Text(art),
        Text.from_markup(
            f"[white][{bar}][/] [dim]{hud.progress.completed}/{hud.progress.total}[/]\n"
            f"[dim]{tok_str}  ·  {hud.model}[/]"
        ),
    )

    if hud.spinning:
        status_widget: Any = Spinner("dots", text=f" {hud.status}", style="cyan")
    else:
        status_widget = Text(f"  {hud.status}", style="dim")

    return Panel(Group(grid, status_widget), title=title, border_style=color)


_PROCESSING_LABELS: dict[str, str] = {
    "intake": "processing your idea",
    "clarify": "generating questions",
    "ideate": "crafting concept",
    "revise": "revising spec",
    "validate": "preparing review",
    "spec_compile": "assembling spec",
    "github_publish": "publishing to GitHub",
    "notify": "sending notifications",
}


_READY = {"/ready", "ready", "/go", "go"}


def _run_graph_loop_v2(
    graph,
    initial_input: dict,
    config: dict,
    progress: _Progress,
    model: str,
) -> None:
    """HITL loop with a persistent Live HUD pinned at the bottom of the terminal."""
    hud = _HUDState(progress=progress, model=model)
    input_to_send = initial_input

    with Live(_make_hud(hud), console=console, refresh_per_second=8, vertical_overflow="visible") as live:
        while True:
            interrupt_payload = None
            hud.spinning = True
            hud.status = "thinking…"
            live.update(_make_hud(hud))

            for chunk in graph.stream(input_to_send, config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupt_payload = chunk["__interrupt__"]
                else:
                    for node_name in chunk:
                        if node_name in DESIGN_NODES:
                            label = DESIGN_NODE_LABELS.get(node_name, node_name)
                            console.print(f"[dim]  ✓ {label}[/]")
                            progress.advance()
                            hud.status = f"✓ {label}"
                        elif node_name in _PROCESSING_LABELS:
                            hud.status = _PROCESSING_LABELS[node_name] + "…"
                    live.update(_make_hud(hud))

            if interrupt_payload is None:
                live.stop()
                _print_completion(dict(graph.get_state(config).values))
                return

            raw = interrupt_payload[0] if isinstance(interrupt_payload, (tuple, list)) else interrupt_payload
            interrupt_value = raw.value if hasattr(raw, "value") else raw
            if not isinstance(interrupt_value, dict):
                interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

            itype = interrupt_value.get("type", "")
            hud.spinning = False
            hud.status = "awaiting input…"
            live.update(_make_hud(hud))
            live.stop()

            user_input = _handle_interrupt(interrupt_value)

            if itype == "ideate" and user_input.strip().lower() in _READY:
                state_vals = dict(graph.get_state(config).values)
                new_creature = select_creature(
                    state_vals.get("raw_idea", ""),
                    state_vals.get("clarifications", []),
                )
                # Animate egg cracking through all frames before revealing
                with Live(console=console, refresh_per_second=6, vertical_overflow="visible") as anim:
                    for frame_idx in range(len(EGG_FRAMES)):
                        hud.egg_frame = frame_idx
                        hud.creature = None
                        hud.status = "hatching…"
                        hud.spinning = False
                        anim.update(_make_hud(hud))
                        time.sleep(0.45)
                hud.creature = new_creature
                progress.advance()
            elif itype in {"intake", "clarify", "validate"}:
                progress.advance()

            hud.spinning = True
            hud.status = "thinking…"
            live.start(refresh=True)
            live.update(_make_hud(hud))

            input_to_send = Command(resume=user_input)


def _print_completion(state: dict) -> None:
    output_path = state.get("output_path", "")
    errors = state.get("errors", [])
    notifications = state.get("notifications_sent", [])
    github_url = state.get("github_output_url", "")

    console.print()
    lines = []
    if output_path:
        size_kb = Path(output_path).stat().st_size / 1024 if Path(output_path).exists() else 0
        lines.append(f"[green]✓[/] Spec written to [bold]{output_path}[/] [dim]({size_kb:.1f} KB)[/]")
    if github_url:
        lines.append(f"[green]✓[/] GitHub: {github_url}")
    for n in notifications:
        status = "[green]✓[/]" if n.get("success") else "[red]✗[/]"
        lines.append(f"{status} {n.get('channel', 'notification')}")
    for e in errors:
        lines.append(f"[yellow]![/] {escape(e)}")

    body = "\n".join(lines) if lines else "[dim]Done.[/]"
    console.print(Panel(body, title="[bold green]theorycraft complete[/]", border_style="green"))


# ── Commands ──────────────────────────────────────────────────────────────

@app.command()
def new(
    idea: Annotated[Optional[str], typer.Argument(help="Product idea (optional — will prompt if omitted)")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Session name")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output directory")] = None,
    github: Annotated[Optional[str], typer.Option("--github", help="GitHub publish mode: repo|pr|gist")] = None,
    github_repo: Annotated[Optional[str], typer.Option("--github-repo", help="Existing repo for PR mode (org/repo)")] = None,
) -> None:
    """Start a new theorycraft session and generate a product spec."""
    from theorycraft.config import get_settings
    from theorycraft.graph.builder import GraphSession
    from theorycraft.graph.state import initial_state
    from theorycraft.mcp.loader import MCPLoader
    from theorycraft.telemetry.langfuse import flush
    from theorycraft.utils import unique_session_name

    import uuid

    cfg = get_settings()
    reset_tokens()
    session_id = str(uuid.uuid4())
    base_name = name or (idea and _slugify(idea)) or f"session-{session_id[:8]}"
    session_name = unique_session_name(base_name, cfg.sessions_dir)
    if session_name != base_name:
        console.print(f"[dim]Session '{base_name}' already exists — using '{session_name}'[/]")
    output_dir = str(output or cfg.output_dir / session_name)

    _print_header(session_name, session_id)

    state = initial_state(
        session_id=session_id,
        session_name=session_name,
        raw_idea=idea or "",
        output_dir=output_dir,
        max_clarify_rounds=cfg.max_clarify_rounds,
        max_revisions=cfg.max_revisions,
    )
    if github:
        state["github_publish_mode"] = github
    if github_repo:
        state["github_existing_repo"] = github_repo

    config = {"configurable": {"thread_id": session_id}}
    db_path = _get_session_db(session_name)

    with MCPLoader() as mcp:
        if mcp.running_servers:
            console.print(f"[dim]MCP servers: {', '.join(mcp.running_servers)}[/]")

        try:
            with GraphSession(db_path) as session:
                progress = _Progress(max_clarify_rounds=cfg.max_clarify_rounds)
                _run_graph_loop_v2(session.graph, state, config, progress, cfg.model)
        finally:
            flush()


@app.command()
def resume(
    session_name: Annotated[str, typer.Argument(help="Session name to resume")],
) -> None:
    """Resume an interrupted theorycraft session."""
    from theorycraft.config import get_settings
    from theorycraft.graph.builder import GraphSession
    from theorycraft.telemetry.langfuse import flush

    db_path = _get_session_db(session_name)
    if not Path(db_path).exists():
        console.print(f"[red]Session '{session_name}' not found.[/]")
        raise typer.Exit(1)

    # Reconstruct session_id from db (use session_name as thread_id fallback)
    config = {"configurable": {"thread_id": session_name}}

    console.print(f"[dim]Resuming session:[/] [yellow]{session_name}[/]")

    cfg = get_settings()
    try:
        with GraphSession(db_path) as session:
            progress = _Progress(max_clarify_rounds=2)
            _run_graph_loop_v2(session.graph, Command(resume=""), config, progress, cfg.model)
    finally:
        flush()


@app.command("list")
def list_sessions() -> None:
    """List all theorycraft sessions."""
    from theorycraft.config import get_settings
    cfg = get_settings()

    sessions_dir = cfg.sessions_dir
    if not sessions_dir.exists():
        console.print("[dim]No sessions yet.[/]")
        return

    db_files = sorted(sessions_dir.glob("*.db"))
    if not db_files:
        console.print("[dim]No sessions yet.[/]")
        return

    table = Table(title="Theorycraft Sessions", show_header=True)
    table.add_column("Session", style="yellow")
    table.add_column("Modified", style="dim")
    table.add_column("Size")

    for f in db_files:
        stat = f.stat()
        import datetime
        mod = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        size = f"{stat.st_size / 1024:.1f} KB"
        table.add_row(f.stem, mod, size)

    console.print(table)


@app.command()
def show(
    session_name: Annotated[str, typer.Argument(help="Session name")],
    spec_path: Annotated[Optional[Path], typer.Option("--spec", "-s", help="Path to product.json (auto-detected if omitted)")] = None,
) -> None:
    """Pretty-print a product spec."""
    from theorycraft.config import get_settings
    cfg = get_settings()

    if spec_path is None:
        # Try default output location
        candidate = cfg.output_dir / session_name / "product.json"
        if not candidate.exists():
            # Try session_id-prefixed version
            candidates = list((cfg.output_dir / session_name).glob("product*.json"))
            if candidates:
                spec_path = candidates[0]
            else:
                console.print(f"[red]No product.json found for session '{session_name}'.[/]")
                raise typer.Exit(1)
        else:
            spec_path = candidate

    try:
        spec = json.loads(spec_path.read_text())
    except Exception as e:
        console.print(f"[red]Failed to read spec: {e}[/]")
        raise typer.Exit(1)

    vision = spec.get("vision", {})
    console.print()
    console.print(Panel(
        f"[bold]{vision.get('name', session_name)}[/]\n"
        f"[dim]{vision.get('tagline', '')}[/]\n\n"
        f"{vision.get('description', '')[:300]}{'...' if len(vision.get('description', '')) > 300 else ''}",
        title="[cyan]Product Vision[/]",
        border_style="cyan",
    ))

    tree = Tree(f"[bold]{vision.get('name', session_name)}[/]")

    services_branch = tree.add(f"[yellow]services[/] ({len(spec.get('services', []))})")
    for s in spec.get("services", []):
        services_branch.add(f"[dim]{s['language']}[/] {s['name']} — {s.get('suggested_framework', '')}")

    routes_branch = tree.add(f"[blue]api_routes[/] ({len(spec.get('api_routes', []))})")
    for r in spec.get("api_routes", [])[:8]:
        routes_branch.add(f"[dim]{r['method']:6}[/] {r['path']}")
    if len(spec.get("api_routes", [])) > 8:
        routes_branch.add(f"[dim]... {len(spec['api_routes']) - 8} more[/]")

    tables = spec.get("db_schema", {}).get("tables", [])
    db_branch = tree.add(f"[green]db_tables[/] ({len(tables)})")
    for t in tables:
        db_branch.add(t["name"])

    pages = spec.get("frontend", {}).get("pages", [])
    fe_branch = tree.add(f"[magenta]frontend[/] ({len(pages)} pages)")
    for p in pages:
        fe_branch.add(f"{p['path']} — {p['name']}")

    sdk_clients = spec.get("sdk", {}).get("clients", [])
    tree.add(f"[cyan]sdk[/] ({len(sdk_clients)} clients)")

    adrs = spec.get("architecture", {}).get("adrs", [])
    tree.add(f"[dim]adrs[/] ({len(adrs)})")

    console.print(tree)
    console.print(f"\n[dim]Source:[/] {spec_path}")


@app.command()
def delete(
    session_name: Annotated[str, typer.Argument(help="Session name to delete")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
    keep_output: Annotated[bool, typer.Option("--keep-output", help="Keep the output directory")] = False,
) -> None:
    """Delete a session checkpoint (and optionally its output directory)."""
    import shutil
    from theorycraft.config import get_settings
    cfg = get_settings()

    db_path = Path(_get_session_db(session_name))
    if not db_path.exists():
        console.print(f"[red]Session '{session_name}' not found.[/]")
        raise typer.Exit(1)

    output_path = cfg.output_dir / session_name

    lines: list[str] = []
    db_kb = db_path.stat().st_size / 1024
    lines.append(f"[dim]checkpoint:[/] {db_path}  [dim]({db_kb:.1f} KB)[/]")

    will_delete_output = not keep_output and output_path.exists()
    if will_delete_output:
        dir_kb = sum(f.stat().st_size for f in output_path.rglob("*") if f.is_file()) / 1024
        lines.append(f"[dim]output dir:[/] {output_path}  [dim]({dir_kb:.1f} KB)[/]")

    console.print(Panel(
        "\n".join(lines),
        title=f"[red]Delete '{session_name}'[/]",
        border_style="red",
    ))

    if not yes:
        confirmed = Prompt.ask("Delete?", choices=["y", "n"], default="n")
        if confirmed != "y":
            console.print("[dim]Cancelled.[/]")
            return

    db_path.unlink()
    console.print(f"[green]✓[/] Deleted checkpoint: {db_path}")

    if will_delete_output:
        shutil.rmtree(output_path)
        console.print(f"[green]✓[/] Deleted output: {output_path}")


@app.command()
def slack() -> None:
    """Start the Slack bot (Socket Mode). Requires SLACK_BOT_TOKEN and SLACK_APP_TOKEN."""
    from theorycraft.slack.app import start
    start()


if __name__ == "__main__":
    app()
