from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SDKParameter(BaseModel):
    name: str
    typescript_type: str
    required: bool = True
    description: Optional[str] = None


class SDKMethod(BaseModel):
    name: str
    description: str
    parameters: list[SDKParameter] = Field(default_factory=list)
    return_type: str
    typescript_signature: str = Field(description="Full TypeScript method signature")
    maps_to_route: Optional[str] = Field(default=None, description="e.g. POST /users")
    example: Optional[str] = None


class SDKClient(BaseModel):
    service_name: str
    class_name: str
    description: str
    methods: list[SDKMethod]
    typescript_types: list[str] = Field(description="TypeScript type/interface definitions")


class FrontendSDK(BaseModel):
    package_name: str = Field(description="e.g. @myapp/client")
    language: str = "typescript"
    clients: list[SDKClient]
    shared_types: list[str] = Field(description="Shared TypeScript type definitions")
    auth_pattern: str = Field(description="How auth tokens are managed in the SDK")
    base_url_config: str = Field(description="How the base URL is configured")
