"""Tests for Pydantic model validation and serialization."""
from __future__ import annotations

import json

import pytest

from theorycraft.models.frontend import FrontendSpec, SPAPage, UIComponent
from theorycraft.models.product import ADR, ArchitectureDecisions, InfrastructureHints, ProductSpec, ProductVision
from theorycraft.models.route import APIResponse, APIRoute
from theorycraft.models.schema import DBSchema, DBTable, SQLColumn
from theorycraft.models.sdk import FrontendSDK, SDKClient, SDKMethod
from theorycraft.models.service import ServiceSpec


def make_product_spec() -> ProductSpec:
    return ProductSpec(
        session_id="test-123",
        vision=ProductVision(
            name="TestApp",
            tagline="Test tagline",
            description="A test product",
            goals=["Goal 1"],
            target_users=["Developers"],
            problem_statement="Testing",
            success_metrics=["10k users"],
        ),
        services=[
            ServiceSpec(
                name="api",
                language="go",
                description="Main API",
                responsibilities=["Handle requests"],
                tech_stack=["gin", "postgres"],
                suggested_framework="gin",
                port=8080,
            )
        ],
        api_routes=[
            APIRoute(
                service_name="api",
                method="GET",
                path="/health",
                summary="Health check",
                responses=[APIResponse(status_code=200, description="OK")],
                auth_required=False,
            )
        ],
        db_schema=DBSchema(
            tables=[
                DBTable(
                    name="users",
                    service_name="api",
                    columns=[
                        SQLColumn(name="id", sql_type="UUID", nullable=False),
                        SQLColumn(name="email", sql_type="TEXT", nullable=False),
                    ],
                    primary_key=["id"],
                )
            ],
            raw_sql="CREATE TABLE users (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT NOT NULL);",
        ),
        frontend=FrontendSpec(
            pages=[SPAPage(path="/", name="Home", description="Landing page")],
            design_notes="Clean, minimal design",
        ),
        sdk=FrontendSDK(
            package_name="@testapp/client",
            clients=[
                SDKClient(
                    service_name="api",
                    class_name="ApiClient",
                    description="Main API client",
                    methods=[
                        SDKMethod(
                            name="healthCheck",
                            description="Check API health",
                            return_type="Promise<void>",
                            typescript_signature="healthCheck(): Promise<void>",
                        )
                    ],
                    typescript_types=[],
                )
            ],
            shared_types=[],
            auth_pattern="Bearer token",
            base_url_config="VITE_API_URL env var",
        ),
        architecture=ArchitectureDecisions(
            adrs=[
                ADR(
                    id="ADR-001",
                    title="Use Go for API",
                    status="accepted",
                    context="Need high throughput",
                    decision="Use Go with gin",
                    rationale="Performance and simplicity",
                    consequences=["Need Go expertise"],
                )
            ],
            tech_choices={"backend": "Go + gin", "database": "PostgreSQL"},
            system_diagram_description="Simple monolith with Postgres",
        ),
        infrastructure=InfrastructureHints(
            deployment_target="Docker Compose",
            required_env_vars=["DATABASE_URL", "JWT_SECRET"],
            suggested_managed_services=["RDS"],
            scaling_notes="Horizontal scaling via container replicas",
            estimated_complexity="low",
        ),
    )


def test_product_spec_roundtrip():
    spec = make_product_spec()
    json_str = spec.model_dump_json(indent=2)
    data = json.loads(json_str)
    restored = ProductSpec.model_validate(data)
    assert restored.vision.name == "TestApp"
    assert restored.services[0].language == "go"
    assert len(restored.api_routes) == 1
    assert restored.api_routes[0].method == "GET"


def test_product_spec_schema_version():
    spec = make_product_spec()
    assert spec.schema_version == "1.0.0"
    assert spec.generated_by == "theorycraft"


def test_service_spec_language_validation():
    with pytest.raises(Exception):
        ServiceSpec(
            name="bad",
            language="java",  # not in Literal["go", "python"]
            description="",
            responsibilities=[],
            tech_stack=[],
            suggested_framework="spring",
        )


def test_api_route_serialization():
    route = APIRoute(
        service_name="api",
        method="POST",
        path="/users",
        summary="Create user",
        responses=[APIResponse(status_code=201, description="Created")],
    )
    data = route.model_dump(by_alias=False)
    assert data["method"] == "POST"
    assert data["path"] == "/users"


def test_db_schema_raw_sql():
    schema = DBSchema(
        tables=[],
        raw_sql="CREATE TABLE test (id UUID PRIMARY KEY);",
    )
    assert "CREATE TABLE" in schema.raw_sql


def test_product_spec_json_file(tmp_path):
    spec = make_product_spec()
    output = tmp_path / "product.json"
    output.write_text(spec.model_dump_json(indent=2))
    assert output.exists()
    restored = ProductSpec.model_validate_json(output.read_text())
    assert restored.session_id == "test-123"
