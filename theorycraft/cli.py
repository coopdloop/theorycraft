from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from langgraph.types import Command
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

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
        return _multiline_prompt(
            "[bold green]>[/]",
            hint="Type /ready when happy, or share feedback (blank line to submit).",
        )

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



def _run_graph_loop_v2(graph, initial_input: dict, config: dict) -> None:
    """HITL loop using graph.stream for real-time design node progress."""
    input_to_send = initial_input

    while True:
        interrupt_payload = None

        for chunk in graph.stream(input_to_send, config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt_payload = chunk["__interrupt__"]
            else:
                for node_name in chunk:
                    if node_name in DESIGN_NODES:
                        label = DESIGN_NODE_LABELS.get(node_name, node_name)
                        console.print(f"[dim]  ✓ {label}[/]")

        if interrupt_payload is None:
            _print_completion(dict(graph.get_state(config).values))
            return

        raw = interrupt_payload[0] if isinstance(interrupt_payload, (tuple, list)) else interrupt_payload
        interrupt_value = raw.value if hasattr(raw, "value") else raw

        if not isinstance(interrupt_value, dict):
            interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

        node_type = interrupt_value.get("type", "")
        if node_type not in {"intake", "clarify", "ideate", "validate"}:
            console.print(f"[dim]  Designing {node_type}...[/]")

        user_input = _handle_interrupt(interrupt_value)
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


@app.command()
def slack() -> None:
    """Start the Slack bot (Socket Mode). Requires SLACK_BOT_TOKEN and SLACK_APP_TOKEN."""
    from theorycraft.slack.app import start
    start()


if __name__ == "__main__":
    app()
