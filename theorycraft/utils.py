from __future__ import annotations

from pathlib import Path

# Design node names and their display labels — used by both CLI and Slack adapter.
DESIGN_NODES = frozenset({
    "service_design",
    "architecture",
    "api_design",
    "database_design",
    "frontend_design",
    "sdk_design",
    "spec_compile",
})

DESIGN_NODE_LABELS: dict[str, str] = {
    "service_design":   "service architecture",
    "architecture":     "architecture decisions",
    "api_design":       "API routes",
    "database_design":  "database schema",
    "frontend_design":  "frontend components",
    "sdk_design":       "TypeScript SDK",
    "spec_compile":     "assembling spec",
}


def unique_session_name(base_name: str, sessions_dir: Path) -> str:
    """Return base_name, or base_name-2, base_name-3, … until no .db file conflicts."""
    candidate = base_name
    n = 2
    while (sessions_dir / f"{candidate}.db").exists():
        candidate = f"{base_name}-{n}"
        n += 1
    return candidate
