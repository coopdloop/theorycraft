from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class JSONSchemaObject(BaseModel):
    type: str
    description: Optional[str] = None
    format: Optional[str] = None
    properties: Optional[dict[str, Any]] = None
    required: Optional[list[str]] = None
    items: Optional[Any] = None
    enum: Optional[list[Any]] = None
    example: Optional[Any] = None


class APIResponse(BaseModel):
    status_code: int
    description: str
    schema_def: Optional[JSONSchemaObject] = Field(default=None, alias="schema")

    model_config = {"populate_by_name": True}


class APIRoute(BaseModel):
    service_name: str = Field(description="Which service owns this route")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(description="URL path with {param} placeholders")
    summary: str
    description: Optional[str] = None
    request_body: Optional[JSONSchemaObject] = None
    path_params: list[str] = Field(default_factory=list)
    query_params: list[str] = Field(default_factory=list)
    responses: list[APIResponse]
    auth_required: bool = True
    tags: list[str] = Field(default_factory=list)
