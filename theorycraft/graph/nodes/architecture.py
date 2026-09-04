from __future__ import annotations

from pydantic import BaseModel

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import safe_structured_call
from theorycraft.models.product import ADR, ArchitectureDecisions
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are a principal software architect writing Architecture Decision Records.
Given the product concept and service list, produce:
1. 3-5 ADRs covering the key architectural decisions (language choice, auth strategy, data storage, etc.)
2. A tech choices map (category → chosen tech + brief rationale)
3. A text description of the system architecture suitable for generating a diagram

Be precise. Each ADR must have a clear decision and concrete consequences.
"""


class ArchitectureOutput(BaseModel):
    architecture: ArchitectureDecisions


@node_trace("architecture")
def architecture(state: TheoryCraftState) -> dict:
    """Generate ADRs and architectural decisions (deterministic)."""
    services_text = ""
    if state.get("services_draft"):
        services_text = "\n".join(
            f"- {s['name']} ({s['language']}): {s['description']}"
            for s in state["services_draft"]
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Product concept:\n{state['concept_summary']}\n\n"
                f"Services:\n{services_text or 'To be determined'}"
            ),
        },
    ]
    result, error = safe_structured_call(ArchitectureOutput, messages, temperature=0.1)
    if result is None:
        return {
            "architecture_draft": {"adrs": [], "tech_choices": {}, "system_diagram_description": ""},
            "errors": [f"architecture failed: {error}"],
        }
    return {"architecture_draft": result.architecture.model_dump()}
