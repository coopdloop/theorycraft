from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from theorycraft.models.frontend import FrontendSpec
from theorycraft.models.route import APIRoute
from theorycraft.models.schema import DBSchema
from theorycraft.models.sdk import FrontendSDK
from theorycraft.models.service import ServiceSpec


class ProductVision(BaseModel):
    name: str
    tagline: str
    description: str
    goals: list[str]
    target_users: list[str]
    problem_statement: str
    success_metrics: list[str]


class ADR(BaseModel):
    id: str = Field(description="e.g. ADR-001")
    title: str
    status: Literal["proposed", "accepted", "deprecated", "superseded"]
    context: str
    decision: str
    rationale: str
    consequences: list[str]


class ArchitectureDecisions(BaseModel):
    adrs: list[ADR]
    tech_choices: dict[str, str] = Field(
        description="Key: technology category, Value: chosen technology with rationale"
    )
    system_diagram_description: str


class InfrastructureHints(BaseModel):
    deployment_target: str = Field(description="e.g. Kubernetes, Docker Compose, Railway")
    required_env_vars: list[str]
    suggested_managed_services: list[str]
    scaling_notes: str
    estimated_complexity: Literal["low", "medium", "high"]


class ProductSpec(BaseModel):
    schema_version: str = "1.0.0"
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generated_by: str = "theorycraft"

    vision: ProductVision
    services: list[ServiceSpec]
    api_routes: list[APIRoute]
    db_schema: DBSchema
    frontend: FrontendSpec
    sdk: FrontendSDK
    architecture: ArchitectureDecisions
    infrastructure: InfrastructureHints

    github_url: Optional[str] = None
