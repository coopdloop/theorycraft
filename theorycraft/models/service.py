from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ServiceDependency(BaseModel):
    service_name: str
    dependency_type: Literal["http", "grpc", "queue", "db"]
    description: Optional[str] = None


class EnvVarSpec(BaseModel):
    name: str
    description: str
    required: bool = True
    example: Optional[str] = None


class ServiceSpec(BaseModel):
    name: str = Field(description="Service name, snake_case")
    language: Literal["go", "python"]
    description: str
    responsibilities: list[str]
    tech_stack: list[str] = Field(description="Key libraries and frameworks")
    suggested_framework: str = Field(description="Primary web framework, e.g. gin, fastapi")
    port: Optional[int] = None
    dependencies: list[ServiceDependency] = Field(default_factory=list)
    environment_variables: list[EnvVarSpec] = Field(default_factory=list)
