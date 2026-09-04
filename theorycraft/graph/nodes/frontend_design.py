from __future__ import annotations

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import safe_structured_call
from theorycraft.models.frontend import FrontendSpec
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are a frontend architect and UX designer with strong opinions about product experience.
Design a React SPA that pairs with the backend services.
You have creative latitude here — be opinionated about:
- Which pages exist and what they accomplish
- Component breakdown and reuse patterns
- State management (prefer zustand unless complexity demands otherwise)
- Design language and visual notes (e.g. "data-dense dashboard with sidebar nav", "mobile-first card-based layout")
- Libraries to reach for (shadcn/ui, radix, react-query, etc.)

The result should feel like a thoughtful product, not just a CRUD interface.
"""


@node_trace("frontend_design")
def frontend_design(state: TheoryCraftState) -> dict:
    """Design the SPA with creative latitude (structured but expressive)."""
    routes_summary = ""
    if state.get("api_routes_draft"):
        routes_summary = "API routes:\n" + "\n".join(
            f"  {r['method']} {r['path']}"
            for r in state["api_routes_draft"][:20]  # cap for context
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Product concept:\n{state['concept_summary']}\n\n"
                f"{routes_summary}"
            ),
        },
    ]
    result, error = safe_structured_call(FrontendSpec, messages, temperature=0.6)
    if result is None:
        return {
            "frontend_draft": {
                "pages": [], "shared_components": [], "design_notes": "",
                "framework": "react", "state_management": "zustand",
                "routing": "react-router-v6",
            },
            "errors": [f"frontend_design failed: {error}"],
        }
    return {"frontend_draft": result.model_dump()}
