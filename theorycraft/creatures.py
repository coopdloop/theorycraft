from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

RARITY_COLOR: dict[str, str] = {
    "Common": "white",
    "Uncommon": "green",
    "Rare": "blue",
    "Epic": "magenta",
    "Legendary": "yellow",
}

_RARITY_MULTIPLIER: dict[str, float] = {
    "Common": 1.0,
    "Uncommon": 1.5,
    "Rare": 3.0,
    "Epic": 6.0,
    "Legendary": 12.0,
}

EGG_FRAMES = [
    "  .----.\n /      \\\n|   ??   |\n \\      /\n  `----'",
    "  .----.\n / *    \\\n|   ??   |\n \\      /\n  `----'",
    "  .-*--.\n / * *  \\\n|  ???   |\n \\ * * /\n  `----'",
    "  .-*-.\n /* * *\\\n| * ? * |\n \\* * */\n  '--*-'",
]


@dataclass
class Creature:
    name: str
    rarity: str
    ascii_art: str
    flavor: str
    base_weight: int


CREATURES: list[Creature] = [
    # ── Common ────────────────────────────────────────────────────────────
    Creature(
        name="Slime",
        rarity="Common",
        ascii_art="  _____\n ( o o )\n(  ~~~  )\n `-----'",
        flavor="A wobbly companion that absorbs everything.",
        base_weight=15,
    ),
    Creature(
        name="Snail",
        rarity="Common",
        ascii_art="  ___\n (. .)>\n  ) (\n `---'",
        flavor="Slow and steady builds the spec.",
        base_weight=15,
    ),
    Creature(
        name="Frog",
        rarity="Common",
        ascii_art="  @   @\n (o . o)\n  \\ v /\n  (___)",
        flavor="Leaps from idea to spec in one bound.",
        base_weight=15,
    ),
    Creature(
        name="Mouse",
        rarity="Common",
        ascii_art=" (/\\  /\\)\n ( o  o )\n  > ^ <\n  '---'",
        flavor="Small but mighty. Chews through requirements.",
        base_weight=15,
    ),
    Creature(
        name="Caterpillar",
        rarity="Common",
        ascii_art=" o~o~o~o\n(^ ^ ^ ^)\n ' ' ' '",
        flavor="Soon to be wings. Your spec is its cocoon.",
        base_weight=15,
    ),
    # ── Uncommon ──────────────────────────────────────────────────────────
    Creature(
        name="Fox",
        rarity="Uncommon",
        ascii_art=" /\\   /\\\n( o   o )\n )     (\n(/\\---/\\)",
        flavor="Cunning architect. Spots edge cases instantly.",
        base_weight=8,
    ),
    Creature(
        name="Owl",
        rarity="Uncommon",
        ascii_art="  {o , o}\n  )     )\n -------",
        flavor="Sees the full system, day and night.",
        base_weight=8,
    ),
    Creature(
        name="Turtle",
        rarity="Uncommon",
        ascii_art="  _____\n /     \\\n| {o o} |\n \\_____/\n   | |",
        flavor="Carries the entire spec on its back.",
        base_weight=8,
    ),
    Creature(
        name="Wolf",
        rarity="Uncommon",
        ascii_art="  /\\ /\\\n ( v  v )\n  ) -- (\n (_|  |_)",
        flavor="Hunts down requirements in a pack.",
        base_weight=8,
    ),
    # ── Rare ──────────────────────────────────────────────────────────────
    Creature(
        name="Dragon",
        rarity="Rare",
        ascii_art="    /\\\n   /oo\\\n  (====)\n   \\  /\n   /||\\",
        flavor="Born to breathe fire into your architecture.",
        base_weight=4,
    ),
    Creature(
        name="Unicorn",
        rarity="Rare",
        ascii_art="   |\n  /^\\\n ( * *)\n  \\_/\n /   \\",
        flavor="Makes the impossible spec feel inevitable.",
        base_weight=4,
    ),
    Creature(
        name="Gryphon",
        rarity="Rare",
        ascii_art=" /\\ /\\\n(>    <)\n ) == (\n \\|  |/",
        flavor="Half eagle vision, half lion execution.",
        base_weight=4,
    ),
    # ── Epic ──────────────────────────────────────────────────────────────
    Creature(
        name="Phoenix",
        rarity="Epic",
        ascii_art="  ~~~~~\n  (>*<)\n   )|(\n  //|\\\\\n // | \\\\",
        flavor="Reborn from every failed MVP. Unstoppable.",
        base_weight=2,
    ),
    Creature(
        name="Kraken",
        rarity="Epic",
        ascii_art="  /~~~\\\n ( o o )\n  \\___/\n /|   |\\\n~~ ~~~ ~~",
        flavor="Its tentacles reach into every microservice.",
        base_weight=2,
    ),
    # ── Legendary ─────────────────────────────────────────────────────────
    Creature(
        name="Ancient Wyrm",
        rarity="Legendary",
        ascii_art=" *  .  *\n  \\|/|/\n --@@@--\n  /|\\|\\\n *  .  *",
        flavor="Existed before the first commit. Knows all patterns.",
        base_weight=1,
    ),
]

_TECH_KEYWORDS = frozenset({
    "api", "database", "real-time", "distributed", "platform", "ml", "ai",
    "saas", "cloud", "microservice", "scalable", "stream", "event", "oauth",
    "websocket", "graph", "vector", "llm",
})


def score_idea(raw_idea: str, clarifications: list) -> float:
    word_score = min(len(raw_idea.split()) / 80, 0.4)
    engagement_score = min(len(clarifications) * 0.1, 0.25)
    idea_lower = raw_idea.lower()
    matches = sum(1 for kw in _TECH_KEYWORDS if kw in idea_lower)
    tech_score = min(matches * 0.05, 0.35)
    return min(word_score + engagement_score + tech_score, 1.0)


def select_creature(raw_idea: str = "", clarifications: list | None = None) -> Creature:
    if clarifications is None:
        clarifications = []
    quality = score_idea(raw_idea, clarifications)
    weights = [
        c.base_weight * (_RARITY_MULTIPLIER[c.rarity] ** quality)
        for c in CREATURES
    ]
    return random.choices(CREATURES, weights=weights, k=1)[0]


def render_egg_panel(console: "Console") -> None:
    from rich.panel import Panel
    console.print(Panel(
        EGG_FRAMES[0],
        title="[dim]hatching soon...[/]",
        border_style="dim",
        expand=False,
    ))


def animate_hatch(console: "Console", creature: Creature) -> None:
    from rich.live import Live
    from rich.panel import Panel

    color = RARITY_COLOR[creature.rarity]

    with Live(console=console, refresh_per_second=4) as live:
        for frame in EGG_FRAMES:
            live.update(Panel(
                frame,
                title="[dim]hatching...[/]",
                border_style="dim",
                expand=False,
            ))
            time.sleep(0.4)

    console.print(Panel(
        creature.ascii_art,
        title=f"[bold {color}]{creature.rarity}[/]  ✨  [bold]{creature.name}[/]",
        subtitle=f"[dim italic]{creature.flavor}[/]",
        border_style=color,
        expand=False,
    ))
