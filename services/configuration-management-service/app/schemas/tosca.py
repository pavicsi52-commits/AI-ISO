"""Request/response schemas for TOSCA template components."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ToscaComponentType


class ConfigurationToscaTemplateCreateRequest(BaseModel):
    """Body of ``POST /configurations/tosca``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_id: UUID | None = None
    component_type: ToscaComponentType
    name: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)
    csar_url: str | None = Field(default=None, max_length=1024)


class ConfigurationToscaTemplateResponse(BaseModel):
    """One TOSCA template component."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID | None
    component_type: ToscaComponentType
    name: str
    content: dict[str, Any]
    csar_url: str | None


__all__ = ["ConfigurationToscaTemplateCreateRequest", "ConfigurationToscaTemplateResponse"]
