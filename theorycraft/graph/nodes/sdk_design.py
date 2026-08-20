from __future__ import annotations

from pydantic import BaseModel

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import structured_call
from theorycraft.models.sdk import FrontendSDK
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are a TypeScript SDK architect designing a typed client library.
Given the API routes, generate a complete SDK spec that the frontend will use.
Rules:
- Create one client class per backend service
- Each method maps to one API route
- Write full TypeScript method signatures (including generics where appropriate)
- Define shared TypeScript types/interfaces for all request/response bodies
- Describe the auth pattern (e.g. Bearer token via Authorization header, stored in memory)
- Package name should be @{product-slug}/client
- Include sensible error handling patterns in method descriptions
- The SDK should be ergonomic and idiomatic TypeScript — use async/await, not callbacks
"""


class SDKOutput(BaseModel):
    sdk: FrontendSDK


@node_trace("sdk_design")
def sdk_design(state: TheoryCraftState) -> dict:
    """Generate TypeScript SDK interface spec (creative, idiomatic)."""
    product_name = state.get("session_name", "app").replace("-", " ").title()

    routes_text = ""
    if state.get("api_routes_draft"):
        routes_text = "API Routes:\n" + "\n".join(
            f"  {r['method']} {r['path']} — {r.get('summary', '')}"
            for r in state["api_routes_draft"]
        )

    services_text = ""
    if state.get("services_draft"):
        services_text = "Services:\n" + "\n".join(
            f"  {s['name']} ({s['language']})"
            for s in state["services_draft"]
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Product: {product_name}\n\n"
                f"{services_text}\n\n"
                f"{routes_text}"
            ),
        },
    ]
    output = structured_call(SDKOutput, messages, temperature=0.4)
    return {"sdk_draft": output.sdk.model_dump()}
