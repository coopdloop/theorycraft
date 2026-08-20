from __future__ import annotations

from pydantic import BaseModel

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import structured_call
from theorycraft.models.route import APIRoute
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are an API designer generating OpenAPI 3.1-compatible route specifications.
Given the product concept and service list, define ALL REST API routes for each service.
Rules:
- Use RESTful conventions (plural nouns, nested resources for ownership)
- Include request body JSON Schema and response JSON Schema for 200/201/400/401/404
- Mark auth_required=True for all routes except /health, /login, /register
- Group routes by service using the service_name field
- Be exhaustive — don't omit CRUD endpoints
"""


class APIRoutesOutput(BaseModel):
    routes: list[APIRoute]


@node_trace("api_design")
def api_design(state: TheoryCraftState) -> dict:
    """Generate complete API route specifications (deterministic)."""
    services_text = ""
    if state.get("services_draft"):
        services_text = "\n".join(
            f"- {s['name']} ({s['language']}): {s.get('description', '')} | "
            f"responsibilities: {', '.join(s.get('responsibilities', []))}"
            for s in state["services_draft"]
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Product concept:\n{state['concept_summary']}\n\n"
                f"Services:\n{services_text or 'TBD'}"
            ),
        },
    ]
    output = structured_call(APIRoutesOutput, messages, temperature=0.1)
    return {"api_routes_draft": [r.model_dump(by_alias=False) for r in output.routes]}
