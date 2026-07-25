"""Request/response schemas for ``/projects/templates``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProjectTemplateCategory


class ProjectTemplateCreateRequest(BaseModel):
    """Body of ``POST /projects/templates``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ProjectTemplateCategory = ProjectTemplateCategory.CUSTOM
    template_version: str = "1.0.0"
    definition: dict[str, Any] = Field(default_factory=dict)


class ProjectTemplateResponse(BaseModel):
    """One reusable project template, in full."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    category: ProjectTemplateCategory
    template_version: str
    is_system: bool
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["ProjectTemplateCreateRequest", "ProjectTemplateResponse"]
