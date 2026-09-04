from __future__ import annotations

from pydantic import BaseModel

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import safe_structured_call
from theorycraft.models.service import ServiceSpec
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are a software architect designing microservice specifications.
Based on the product concept, identify all backend services needed (Go or Python).
For each service specify: name, language, responsibilities, tech stack, framework, port, env vars.
Be opinionated and specific. Prefer Go for API gateways and high-throughput services.
Prefer Python for ML, data pipelines, or scripting-heavy services.
"""


class ServiceDesignOutput(BaseModel):
    services: list[ServiceSpec]
    rationale: str


@node_trace("service_design")
def service_design(state: TheoryCraftState) -> dict:
    """Design backend service architecture (deterministic structured output)."""
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"Product concept:\n{state['concept_summary']}",
        },
    ]
    result, error = safe_structured_call(ServiceDesignOutput, messages, temperature=0.1)
    if result is None:
        return {"services_draft": [], "errors": [f"service_design failed: {error}"]}
    return {
        "services_draft": [s.model_dump() for s in result.services],
    }
