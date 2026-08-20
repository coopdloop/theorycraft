from __future__ import annotations

from pydantic import BaseModel

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import structured_call
from theorycraft.models.schema import DBSchema, DBTable
from theorycraft.telemetry.langfuse import node_trace

_SYSTEM = """\
You are a database architect generating SQLC-compatible PostgreSQL schemas.
Given the product concept, services, and API routes, design the complete database schema.
Rules:
- Use UUIDs as primary keys (type: UUID DEFAULT gen_random_uuid())
- Include created_at / updated_at on every table (TIMESTAMPTZ NOT NULL DEFAULT NOW())
- Add appropriate indexes for foreign keys and common query patterns
- Write the complete raw_sql as a single migration file with all CREATE TABLE statements
- Assign each table to the service that owns it
- Use snake_case for all identifiers
"""


class DBDesignOutput(BaseModel):
    db_schema: DBSchema


@node_trace("database_design")
def database_design(state: TheoryCraftState) -> dict:
    """Generate SQLC-compatible PostgreSQL schema (deterministic)."""
    routes_summary = ""
    if state.get("api_routes_draft"):
        unique_resources = set()
        for r in state["api_routes_draft"]:
            parts = [p for p in r["path"].split("/") if p and not p.startswith("{")]
            if parts:
                unique_resources.add(parts[-1])
        routes_summary = "Key resources: " + ", ".join(sorted(unique_resources))

    services_text = ""
    if state.get("services_draft"):
        services_text = "\n".join(f"- {s['name']}" for s in state["services_draft"])

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Product concept:\n{state['concept_summary']}\n\n"
                f"Services:\n{services_text or 'TBD'}\n\n"
                f"{routes_summary}"
            ),
        },
    ]
    output = structured_call(DBDesignOutput, messages, temperature=0.1)
    return {"db_schema_draft": output.db_schema.model_dump()}
