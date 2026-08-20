from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

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
        console.print(Panel(
            escape(interrupt_payload.get("questions", "")),
            title=f"[yellow]clarify[/] [dim](round {interrupt_payload.get('round', 1)})[/]",
            border_style="yellow",
        ))
        console.print("[dim]Answer all questions. Press Enter after each, or give a combined answer.[/]")
        return Prompt.ask("[bold yellow]>[/]")

    elif interrupt_type == "ideate":
        console.print()
        console.print(Panel(
            escape(interrupt_payload.get("concept", "")),
            title=f"[green]theorycraft[/] [dim](round {interrupt_payload.get('round', 1)})[/]",
            border_style="green",
        ))
        console.print("[dim]Steer the direction, add ideas, or type [bold]/ready[/] to build the spec.[/]")
        return Prompt.ask("[bold green]>[/]")

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


def _run_graph_loop(
    graph,
    initial_input: dict,
    config: dict,
    *,
    skip_intake: bool = False,
) -> None:
    """Main HITL loop — streams graph, handles interrupts, resumes on user input."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Starting session...", total=None)

        # First invocation
        input_to_send = initial_input

        while True:
            try:
                current_node = None
                for chunk in graph.stream(input_to_send, config, stream_mode="values"):
                    # chunk is the full state after each node fires
                    pass  # state updates are handled via interrupt

                # Graph completed without interrupt
                progress.stop()
                break

            except GraphInterrupt as exc:
                progress.stop()
                interrupt_value = exc.args[0] if exc.args else {}

                # Handle list of interrupts (LangGraph wraps in a list)
                if isinstance(interrupt_value, list) and interrupt_value:
                    interrupt_value = interrupt_value[0].value if hasattr(interrupt_value[0], "value") else interrupt_value[0]

                user_input = _handle_interrupt(
                    interrupt_value if isinstance(interrupt_value, dict) else {"type": "unknown", "prompt": str(interrupt_value)}
                )

                # Show which node we're advancing past
                node_hint = interrupt_value.get("type", "") if isinstance(interrupt_value, dict) else ""
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as p:
                    p.add_task(f"[dim]Processing {node_hint}...[/]", total=None)
                    input_to_send = Command(resume=user_input)
                    progress = p
                    progress.start()
                    break  # restart outer loop


def _run_graph_loop_v2(graph, initial_input: dict, config: dict) -> None:
    """Cleaner HITL loop using invoke pattern for interrupt/resume."""
    input_to_send = initial_input
    is_resuming = False

    while True:
        try:
            if is_resuming:
                # Resume with Command(resume=...) — state is reconstructed from checkpoint
                result = graph.invoke(input_to_send, config)
            else:
                result = graph.invoke(input_to_send, config)
            # Graph finished
            _print_completion(result)
            return

        except GraphInterrupt as exc:
            interrupt_value = exc.args[0] if exc.args else {}

            # Unwrap if list
            if isinstance(interrupt_value, (list, tuple)) and interrupt_value:
                item = interrupt_value[0]
                interrupt_value = item.value if hasattr(item, "value") else item

            if not isinstance(interrupt_value, dict):
                interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

            node_type = interrupt_value.get("type", "")

            # Show progress spinner for design nodes
            if node_type not in {"intake", "clarify", "ideate", "validate"}:
                console.print(f"[dim]  Designing {node_type}...[/]")

            user_input = _handle_interrupt(interrupt_value)
            input_to_send = Command(resume=user_input)
            is_resuming = True


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

    import uuid

    cfg = get_settings()
    session_id = str(uuid.uuid4())
    session_name = name or (idea and _slugify(idea)) or f"session-{session_id[:8]}"
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
                _run_graph_loop_v2(session.graph, state, config)
        finally:
            flush()


@app.command()
def resume(
    session_name: Annotated[str, typer.Argument(help="Session name to resume")],
) -> None:
    """Resume an interrupted theorycraft session."""
    from theorycraft.graph.builder import GraphSession
    from theorycraft.telemetry.langfuse import flush

    db_path = _get_session_db(session_name)
    if not Path(db_path).exists():
        console.print(f"[red]Session '{session_name}' not found.[/]")
        raise typer.Exit(1)

    # Reconstruct session_id from db (use session_name as thread_id fallback)
    config = {"configurable": {"thread_id": session_name}}

    console.print(f"[dim]Resuming session:[/] [yellow]{session_name}[/]")

    try:
        with GraphSession(db_path) as session:
            # Resume with no new input — the graph will re-raise the pending interrupt
            _run_graph_loop_v2(session.graph, Command(resume=""), config)
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


if __name__ == "__main__":
    app()
