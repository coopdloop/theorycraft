from __future__ import annotations

import json
from pathlib import Path

from theorycraft import naming
from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import simple_call
from theorycraft.models.product import (
    ADR,
    ArchitectureDecisions,
    InfrastructureHints,
    ProductSpec,
    ProductVision,
)
from theorycraft.models.frontend import FrontendSpec
from theorycraft.models.route import APIRoute
from theorycraft.models.schema import DBSchema
from theorycraft.models.sdk import FrontendSDK
from theorycraft.models.service import ServiceSpec
from theorycraft.telemetry.langfuse import node_trace

_VISION_SYSTEM = """\
Extract a structured product vision from the concept summary.
Return ONLY a JSON object with these fields:
name, tagline, description, goals (list), target_users (list), problem_statement, success_metrics (list)

"name" is the product's actual name — 1-3 words, no sentence fragments, no filler like "a" or "the".
It becomes the GitHub repo name, so keep it short and distinctive.
"""

_INFRA_SYSTEM = """\
Based on the product services and architecture, suggest infrastructure hints.
Return ONLY a JSON object with:
deployment_target (string), required_env_vars (list of strings),
suggested_managed_services (list of strings), scaling_notes (string),
estimated_complexity ("low"|"medium"|"high")
"""


def _extract_vision(concept: str, known_name: str = "") -> ProductVision:
    resp = simple_call(
        [
            {"role": "system", "content": _VISION_SYSTEM},
            {"role": "user", "content": concept},
        ],
        temperature=0.1,
    )
    try:
        # Strip markdown code fences if present
        cleaned = resp.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        vision = ProductVision(**data)
        # The ideation step already agreed a name with the user — trust it when
        # the extractor returned something vaguer than what we already knew.
        if known_name and not vision.name.strip():
            vision.name = known_name
        return vision
    except Exception:
        # Fallback minimal vision
        return ProductVision(
            name=known_name or naming.title_from_concept(concept),
            tagline="",
            description=concept[:500],
            goals=[],
            target_users=[],
            problem_statement="",
            success_metrics=[],
        )


def _extract_infra(state: TheoryCraftState) -> InfrastructureHints:
    services_text = ""
    if state.get("services_draft"):
        services_text = "\n".join(
            f"- {s['name']} ({s['language']})"
            for s in state["services_draft"]
        )
    arch_text = ""
    if state.get("architecture_draft") and state["architecture_draft"].get("tech_choices"):
        arch_text = str(state["architecture_draft"]["tech_choices"])

    resp = simple_call(
        [
            {"role": "system", "content": _INFRA_SYSTEM},
            {
                "role": "user",
                "content": f"Services:\n{services_text}\n\nTech choices:\n{arch_text}",
            },
        ],
        temperature=0.1,
    )
    try:
        cleaned = resp.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        return InfrastructureHints(**data)
    except Exception:
        return InfrastructureHints(
            deployment_target="Docker Compose",
            required_env_vars=[],
            suggested_managed_services=[],
            scaling_notes="",
            estimated_complexity="medium",
        )


@node_trace("spec_compile")
def spec_compile(state: TheoryCraftState) -> dict:
    """Assemble all design drafts into the final ProductSpec JSON."""
    agreed_name = (state.get("product_name") or "").strip()
    vision = _extract_vision(state.get("concept_summary", ""), agreed_name)

    services = [ServiceSpec(**s) for s in (state.get("services_draft") or [])]
    api_routes = [APIRoute(**r) for r in (state.get("api_routes_draft") or [])]

    db_schema_data = state.get("db_schema_draft") or {"tables": [], "raw_sql": ""}
    db_schema = DBSchema(**db_schema_data)

    frontend_data = state.get("frontend_draft") or {
        "pages": [], "shared_components": [], "design_notes": "", "framework": "react",
        "state_management": "zustand", "routing": "react-router-v6",
    }
    frontend = FrontendSpec(**frontend_data)

    sdk_data = state.get("sdk_draft") or {
        "package_name": f"@{naming.package_scope(vision.name)}/client",
        "language": "typescript",
        "clients": [],
        "shared_types": [],
        "auth_pattern": "",
        "base_url_config": "",
    }
    sdk = FrontendSDK(**sdk_data)

    arch_data = state.get("architecture_draft") or {"adrs": [], "tech_choices": {}, "system_diagram_description": ""}
    arch = ArchitectureDecisions(**arch_data)

    infra = _extract_infra(state)

    spec = ProductSpec(
        session_id=state["session_id"],
        vision=vision,
        services=services,
        api_routes=api_routes,
        db_schema=db_schema,
        frontend=frontend,
        sdk=sdk,
        architecture=arch,
        infrastructure=infra,
    )

    output_dir = Path(state.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "product.json"

    # Avoid clobbering — append session_id if file exists
    if output_path.exists():
        output_path = output_dir / f"product_{state['session_id'][:8]}.json"

    output_path.write_text(spec.model_dump_json(indent=2, by_alias=False))
    return {"output_path": str(output_path)}
