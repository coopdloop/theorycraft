from __future__ import annotations

from langgraph.types import interrupt

from theorycraft.graph.state import RevisionRequest, TheoryCraftState
from theorycraft.telemetry.langfuse import node_trace


def _build_summary(state: TheoryCraftState) -> str:
    lines = []
    if state.get("services_draft"):
        names = [s["name"] for s in state["services_draft"]]
        lines.append(f"services ({len(names)}): {', '.join(names)}")
    if state.get("api_routes_draft"):
        lines.append(f"api_routes ({len(state['api_routes_draft'])})")
    if state.get("db_schema_draft") and state["db_schema_draft"].get("tables"):
        tables = [t["name"] for t in state["db_schema_draft"]["tables"]]
        lines.append(f"db_tables ({len(tables)}): {', '.join(tables)}")
    if state.get("frontend_draft") and state["frontend_draft"].get("pages"):
        pages = [p["name"] for p in state["frontend_draft"]["pages"]]
        lines.append(f"frontend ({len(pages)} pages): {', '.join(pages)}")
    if state.get("sdk_draft") and state["sdk_draft"].get("clients"):
        lines.append(f"sdk ({len(state['sdk_draft']['clients'])} clients)")
    if state.get("architecture_draft") and state["architecture_draft"].get("adrs"):
        lines.append(f"adrs ({len(state['architecture_draft']['adrs'])})")
    return "\n  ".join(lines) if lines else "  (no sections generated yet)"


@node_trace("validate")
def validate(state: TheoryCraftState) -> dict:
    """HITL: present spec summary and let user approve or request revisions."""
    summary = _build_summary(state)
    revision_round = state.get("revision_round", 0)

    result = interrupt(
        {
            "type": "validate",
            "summary": summary,
            "revision_round": revision_round,
            "hint": (
                "Commands: [approve] write the spec  "
                "[revise <section>: <feedback>] change a section  "
                "[restart] go back to ideation"
            ),
        }
    )

    user_input: str = result if isinstance(result, str) else result.get("input", "")
    cmd = user_input.strip().lower()

    if cmd in {"approve", "/approve", "yes", "y", "done"}:
        return {"spec_approved": True}

    if cmd in {"restart", "/restart", "back", "/back"}:
        return {
            "spec_approved": False,
            "concept_approved": False,
            "sections_to_revise": [],
        }

    if cmd.startswith("revise ") or ":" in cmd:
        section, _, feedback = user_input.partition(":")
        section = section.replace("revise", "").strip()
        feedback = feedback.strip() or "User requested revisions"
        req = RevisionRequest(
            section=section,
            feedback=feedback,
            round=revision_round + 1,
        )
        return {
            "spec_approved": False,
            "sections_to_revise": [req],
            "revision_round": revision_round + 1,
        }

    # Treat free-form input as general revision request
    req = RevisionRequest(section="general", feedback=user_input, round=revision_round + 1)
    return {
        "spec_approved": False,
        "sections_to_revise": [req],
        "revision_round": revision_round + 1,
    }
