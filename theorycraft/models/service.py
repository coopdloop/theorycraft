from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ServiceDependency(BaseModel):
    service_name: str
    dependency_type: Literal["http", "grpc", "queue", "db"]
    description: Optional[str] = None


class EnvVarSpec(BaseModel):
    name: str
    description: str
    required: bool = True
    example: Optional[str] = None

    @field_validator("example", mode="before")
    @classmethod
    def coerce_example(cls, v: object) -> Optional[str]:
        return None if v is None else str(v)


class ServiceSpec(BaseModel):
    name: str = Field(description="Service name, snake_case")
    language: Literal["go", "python"]
    description: str
    responsibilities: list[str]
    tech_stack: list[str] = Field(default_factory=list, description="Key libraries and frameworks")
    suggested_framework: str = Field(default="", description="Primary web framework, e.g. gin, fastapi")
    port: Optional[int] = None
    dependencies: list[ServiceDependency] = Field(default_factory=list)
    environment_variables: list[EnvVarSpec] = Field(default_factory=list)
