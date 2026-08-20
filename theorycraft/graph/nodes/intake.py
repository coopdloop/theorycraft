from __future__ import annotations

from langgraph.types import interrupt

from theorycraft.graph.state import TheoryCraftState
from theorycraft.telemetry.langfuse import node_trace


@node_trace("intake")
def intake(state: TheoryCraftState) -> dict:
    """Collect the user's raw product idea and any additional context."""
    # If raw_idea already set (e.g. from CLI arg), skip the interrupt
    if state.get("raw_idea"):
        return {}

    result = interrupt(
        {
            "type": "intake",
            "prompt": "What idea would you like to theorycraft today?",
            "hint": "Describe your product idea. Be as specific or vague as you like — we'll refine it together.",
        }
    )

    raw_idea: str = result if isinstance(result, str) else result.get("idea", "")
    return {"raw_idea": raw_idea}
