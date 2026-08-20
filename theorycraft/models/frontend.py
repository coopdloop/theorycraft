from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UIComponent(BaseModel):
    name: str
    description: str
    props: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SPAPage(BaseModel):
    path: str
    name: str
    description: str
    auth_required: bool = False
    components: list[UIComponent] = Field(default_factory=list)
    state_slice: Optional[str] = Field(default=None, description="Which state slice this page reads")


class FrontendSpec(BaseModel):
    framework: str = "react"
    state_management: str = Field(default="zustand", description="State management library")
    routing: str = Field(default="react-router-v6")
    pages: list[SPAPage]
    shared_components: list[UIComponent] = Field(default_factory=list)
    design_notes: str = Field(description="Creative design direction and visual language")
    theme: Optional[str] = Field(default=None, description="e.g. shadcn/ui + tailwind")
