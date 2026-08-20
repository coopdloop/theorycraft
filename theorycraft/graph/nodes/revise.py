from __future__ import annotations

from theorycraft.graph.nodes.api_design import api_design
from theorycraft.graph.nodes.architecture import architecture
from theorycraft.graph.nodes.database_design import database_design
from theorycraft.graph.nodes.frontend_design import frontend_design
from theorycraft.graph.nodes.sdk_design import sdk_design
from theorycraft.graph.nodes.service_design import service_design
from theorycraft.graph.state import TheoryCraftState
from theorycraft.telemetry.langfuse import node_trace

_SECTION_MAP = {
    "services": service_design,
    "service": service_design,
    "architecture": architecture,
    "arch": architecture,
    "api": api_design,
    "api_routes": api_design,
    "routes": api_design,
    "database": database_design,
    "db": database_design,
    "schema": database_design,
    "db_schema": database_design,
    "frontend": frontend_design,
    "ui": frontend_design,
    "sdk": sdk_design,
}


@node_trace("revise")
def revise(state: TheoryCraftState) -> dict:
    """Re-run specific design nodes based on user revision requests."""
    requests = state.get("sections_to_revise", [])
    if not requests:
        return {}

    updates: dict = {}
    processed_fns: set = set()

    for req in requests:
        section = req["section"].strip().lower()
        feedback = req.get("feedback", "")

        # Inject revision feedback into concept_summary temporarily
        revision_context = (
            f"{state['concept_summary']}\n\n"
            f"[REVISION REQUEST for {section}]: {feedback}"
        )
        augmented_state = {**state, "concept_summary": revision_context}

        # Handle 'general' — re-run all
        if section in {"general", "all", "everything"}:
            fns = list(_SECTION_MAP.values())
        else:
            fn = _SECTION_MAP.get(section)
            fns = [fn] if fn else []

        for fn in fns:
            fn_id = id(fn)
            if fn_id not in processed_fns:
                result = fn(augmented_state)
                updates.update(result)
                processed_fns.add(fn_id)

    # Clear processed revision requests
    updates["sections_to_revise"] = []
    return updates
