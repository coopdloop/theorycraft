from __future__ import annotations

import queue
import re
import threading
from pathlib import Path
from typing import Any, Optional

from langgraph.types import Command
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Label, RichLog, Static

from theorycraft.creatures import EGG_FRAMES, RARITY_COLOR, Creature, select_creature
from theorycraft.llm.router import get_total_tokens
from theorycraft.utils import DESIGN_NODE_LABELS, DESIGN_NODES

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


def _parse_questions(text: str) -> list[str]:
    parts = re.split(r"\n\s*\d+[.)]\s*", text.strip())
    questions = [p.strip() for p in parts if p.strip()]
    return questions if len(questions) > 1 else [text.strip()]


# ── HUD sidebar ───────────────────────────────────────────────────────────────

class HUDWidget(Static):
    """Fixed left sidebar: egg/creature art, progress bar, token count, status."""

    _SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    DEFAULT_CSS = """
    HUDWidget {
        width: 30;
        border-right: solid $accent-darken-2;
    }
    """

    def __init__(self, progress_total: int, model: str, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._progress_total = progress_total
        self._model = model.split("/")[-1]
        self._creature: Optional[Creature] = None
        self._egg_frame: int = 0
        self._status: str = "starting…"
        self._spinning: bool = True
        self._progress_completed: int = 0
        self._spin_idx: int = 0

    def on_mount(self) -> None:
        self.set_interval(1 / 8, self._tick)

    def render(self) -> Panel:  # Textual calls this; Rich Panel is valid here
        return self._build_panel()

    def _tick(self) -> None:
        if self._spinning:
            self._spin_idx = (self._spin_idx + 1) % len(self._SPIN)
        self.refresh()

    def update_hud(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, f"_{k}", v)
        self.refresh()

    def _build_panel(self) -> Panel:
        if self._creature:
            art = self._creature.ascii_art
            color = RARITY_COLOR.get(self._creature.rarity, "white")
            title = f"[bold {color}]{self._creature.rarity}[/] ✨ [bold]{self._creature.name}[/]"
        else:
            art = EGG_FRAMES[self._egg_frame]
            color = "dim"
            title = "[dim]egg[/]"

        bw = 12
        filled = int(bw * self._progress_completed / max(self._progress_total, 1))
        bar = "█" * filled + "░" * (bw - filled)
        tokens = get_total_tokens()
        tok_str = f"{tokens:,}" if tokens < 10_000 else f"{tokens / 1000:.1f}k"
        spin = self._SPIN[self._spin_idx] if self._spinning else " "

        grid = Table.grid()
        grid.add_column(no_wrap=False)
        grid.add_row(Text(art))
        grid.add_row(Text(""))
        grid.add_row(Text.from_markup(
            f"[white][{bar}][/] [dim]{self._progress_completed}/{self._progress_total}[/]\n"
            f"[dim]{tok_str} tok[/]\n"
            f"[dim]{self._model}[/]"
        ))
        grid.add_row(Text(""))
        grid.add_row(Text.from_markup(
            f"[cyan]{spin}[/] [dim]{self._status}[/]"
            if self._spinning
            else f"  [dim]{self._status}[/]"
        ))

        return Panel(grid, title=title, border_style=color, expand=True)


# ── Main app ──────────────────────────────────────────────────────────────────

class TheoryCraftApp(App[None]):
    """Full-screen Textual TUI for a theorycraft session."""

    BINDINGS = [
        Binding("q", "maybe_quit", "Quit", show=False),
        Binding("escape", "maybe_quit", "Quit", show=False),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #header {
        height: 3;
        padding: 1 2;
        background: $panel-darken-1;
        border-bottom: solid $accent-darken-2;
    }

    #body {
        layout: horizontal;
        height: 1fr;
    }

    RichLog {
        width: 1fr;
        padding: 0 1;
    }

    #input-row {
        height: 3;
        layout: horizontal;
        border-top: solid $accent-darken-2;
        align: left middle;
        padding: 0 1;
    }

    #input-prefix {
        width: auto;
        padding: 0 1;
        color: $accent;
        content-align: center middle;
    }

    Input {
        width: 1fr;
        border: none;
        background: transparent;
        padding: 0 0;
    }

    Input:focus {
        border: none;
    }
    """

    def __init__(
        self,
        graph: Any,
        initial_input: Any,
        config: dict,
        session_name: str,
        model: str,
        max_clarify_rounds: int,
        lf_enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.graph = graph
        self.initial_input = initial_input
        self.config = config
        self.session_name = session_name
        self.model = model
        self.lf_enabled = lf_enabled
        self._progress_total = 1 + max_clarify_rounds + 1 + 7 + 1 + 1
        self._progress_completed = 0
        self._input_queue: queue.Queue[str] = queue.Queue()
        self._input_event = threading.Event()
        self._hud: Optional[HUDWidget] = None
        self._log: Optional[RichLog] = None
        self._session_done = False

    def compose(self) -> ComposeResult:
        model_short = self.model.split("/")[-1]
        lf = "[green]langfuse[/]  ·  " if self.lf_enabled else ""
        yield Label(
            f"[bold cyan]theorycraft[/]  ·  [yellow]{self.session_name}[/]  ·  "
            f"[dim]{lf}{model_short}[/]",
            id="header",
        )
        with Horizontal(id="body"):
            yield HUDWidget(self._progress_total, self.model, id="hud")
            yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        with Horizontal(id="input-row"):
            yield Label("[dim]>[/]", id="input-prefix")
            yield Input(placeholder="waiting for session to start…", id="input", disabled=True)

    def on_mount(self) -> None:
        self._hud = self.query_one("#hud", HUDWidget)
        self._log = self.query_one("#log", RichLog)
        self._start_graph()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_maybe_quit(self) -> None:
        if self._session_done:
            self.exit()

    # ── UI-thread helpers ─────────────────────────────────────────────────────

    def _write(self, renderable: Any) -> None:
        assert self._log is not None
        self._log.write(renderable)

    def _set_input_enabled(self, label: str) -> None:
        self.query_one("#input-prefix", Label).update(f"{label} [dim]>[/] ")
        inp = self.query_one("#input", Input)
        inp.disabled = False
        inp.placeholder = ""
        inp.focus()
        assert self._hud is not None
        self._hud.update_hud(status="awaiting input…", spinning=False)

    def _set_input_disabled(self, echoed: str) -> None:
        self._write(Text.from_markup(f"[dim]> {escape(echoed)}[/]"))
        inp = self.query_one("#input", Input)
        inp.disabled = True
        inp.placeholder = "thinking…"
        assert self._hud is not None
        self._hud.update_hud(status="thinking…", spinning=True)

    def _advance_progress(self) -> None:
        self._progress_completed = min(self._progress_completed + 1, self._progress_total)
        assert self._hud is not None
        self._hud.update_hud(progress_completed=self._progress_completed)

    # ── Interrupt display (UI thread) ─────────────────────────────────────────

    def _show_interrupt(self, interrupt_value: dict) -> None:
        itype = interrupt_value.get("type", "unknown")

        if itype == "intake":
            self._write(Panel(
                "[bold]What idea would you like to theorycraft today?[/]\n"
                "[dim]Describe your product idea — be as specific or vague as you like.[/]",
                title="[cyan]intake[/]", border_style="cyan",
            ))
            self._set_input_enabled("[bold cyan]idea[/]")

        elif itype == "clarify":
            questions = _parse_questions(interrupt_value.get("questions", ""))
            rnd = interrupt_value.get("round", 1)
            for i, q in enumerate(questions, 1):
                self._write(Panel(
                    escape(q),
                    title=f"[yellow]clarify[/] [dim](round {rnd} · {i}/{len(questions)})[/]",
                    border_style="yellow",
                ))
            self._set_input_enabled("[bold yellow]answer[/]")

        elif itype == "ideate":
            self._write(Panel(
                escape(interrupt_value.get("concept", "")),
                title=f"[green]theorycraft[/] [dim](round {interrupt_value.get('round', 1)})[/]",
                border_style="green",
            ))
            self._write(Text.from_markup(
                "[dim]Type [bold]/ready[/] to proceed, or share feedback.[/]"
            ))
            self._set_input_enabled("[bold green]/ready[/]")

        elif itype == "validate":
            summary_lines = interrupt_value.get("summary", "").split("\n  ")
            tree = Tree("[bold]Spec Preview[/]")
            for line in summary_lines:
                if line.strip():
                    tree.add(escape(line.strip()))
            self._write(Panel(tree, title="[magenta]review[/]", border_style="magenta"))
            self._write(Text.from_markup(
                "[dim]Commands: [bold]approve[/] · [bold]revise <section>: <feedback>[/] · [bold]restart[/][/]"
            ))
            self._set_input_enabled("[bold magenta]review[/]")

        else:
            self._write(Panel(escape(str(interrupt_value)), title="[red]interrupt[/]", border_style="red"))
            self._set_input_enabled("[bold]>[/]")

    def _on_design_complete(self, label: str) -> None:
        self._write(Text.from_markup(f"[dim]  ✓ {label}[/]"))
        self._advance_progress()
        assert self._hud is not None
        self._hud.update_hud(status=f"✓ {label}", spinning=True)

    def _on_processing(self, status: str) -> None:
        assert self._hud is not None
        self._hud.update_hud(status=status, spinning=True)

    # ── Hatch animation (UI thread, timer chain) ──────────────────────────────

    def _do_hatch(self, creature: Creature) -> None:
        self._hatch_frame(0, creature)

    def _hatch_frame(self, idx: int, creature: Creature) -> None:
        assert self._hud is not None
        if idx < len(EGG_FRAMES):
            self._hud.update_hud(egg_frame=idx, creature=None, status="hatching…", spinning=False)
            self.set_timer(0.4, lambda: self._hatch_frame(idx + 1, creature))
        else:
            self._hud.update_hud(creature=creature, status="hatched!", spinning=False)
            color = RARITY_COLOR.get(creature.rarity, "white")
            self._write(Panel(
                Text(creature.ascii_art),
                title=f"[bold {color}]{creature.rarity}[/]  ✨  [bold]{creature.name}[/]",
                subtitle=f"[dim italic]{creature.flavor}[/]",
                border_style=color,
                expand=False,
            ))

    # ── Completion (UI thread) ────────────────────────────────────────────────

    def _on_complete(self, state: dict) -> None:
        output_path = state.get("output_path", "")
        github_url = state.get("github_output_url", "")
        lines: list[str] = []
        if output_path:
            size_kb = Path(output_path).stat().st_size / 1024 if Path(output_path).exists() else 0
            lines.append(
                f"[green]✓[/] Spec written to [bold]{output_path}[/] [dim]({size_kb:.1f} KB)[/]"
            )
        if github_url:
            lines.append(f"[green]✓[/] GitHub: {github_url}")
        for n in state.get("notifications_sent", []):
            s = "[green]✓[/]" if n.get("success") else "[red]✗[/]"
            lines.append(f"{s} {n.get('channel', 'notification')}")
        for e in state.get("errors", []):
            lines.append(f"[yellow]![/] {escape(e)}")
        body = "\n".join(lines) if lines else "[dim]Done.[/]"
        self._write(Panel(body, title="[bold green]theorycraft complete[/]", border_style="green"))
        assert self._hud is not None
        self._hud.update_hud(status="complete!", spinning=False)
        self._session_done = True
        inp = self.query_one("#input", Input)
        inp.disabled = True
        inp.placeholder = "session complete — press q or esc to exit"

    # ── Input handling (UI thread) ────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return
        event.input.clear()
        self._set_input_disabled(user_input)
        self._input_queue.put(user_input)
        self._input_event.set()

    # ── Worker thread: graph execution ────────────────────────────────────────

    def _request_user_input(self, interrupt_value: dict) -> str:
        self.call_from_thread(self._show_interrupt, interrupt_value)
        self._input_event.wait()
        self._input_event.clear()
        return self._input_queue.get()

    @work(thread=True)
    def _start_graph(self) -> None:
        input_to_send = self.initial_input
        hud = self._hud  # cached reference, safe to read from thread

        while True:
            interrupt_payload = None
            self.call_from_thread(hud.update_hud, status="thinking…", spinning=True)

            for chunk in self.graph.stream(input_to_send, self.config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupt_payload = chunk["__interrupt__"]
                else:
                    for node_name in chunk:
                        if node_name in DESIGN_NODES:
                            label = DESIGN_NODE_LABELS.get(node_name, node_name)
                            self.call_from_thread(self._on_design_complete, label)
                        elif node_name in _PROCESSING_LABELS:
                            self.call_from_thread(
                                self._on_processing,
                                _PROCESSING_LABELS[node_name] + "…",
                            )

            if interrupt_payload is None:
                state = dict(self.graph.get_state(self.config).values)
                self.call_from_thread(self._on_complete, state)
                return

            raw = (
                interrupt_payload[0]
                if isinstance(interrupt_payload, (tuple, list))
                else interrupt_payload
            )
            interrupt_value = raw.value if hasattr(raw, "value") else raw
            if not isinstance(interrupt_value, dict):
                interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

            user_input = self._request_user_input(interrupt_value)
            itype = interrupt_value.get("type", "")

            if itype == "ideate" and user_input.lower() in _READY:
                state_vals = dict(self.graph.get_state(self.config).values)
                creature = select_creature(
                    state_vals.get("raw_idea", ""),
                    state_vals.get("clarifications", []),
                )
                self.call_from_thread(self._do_hatch, creature)
                self.call_from_thread(self._advance_progress)
            elif itype in {"intake", "clarify", "validate"}:
                self.call_from_thread(self._advance_progress)

            input_to_send = Command(resume=user_input)
