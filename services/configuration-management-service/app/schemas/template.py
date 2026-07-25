"""Request/response schemas for ``/configurations/templates``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ConfigurationType


class ConfigurationTemplateCreateRequest(BaseModel):
    """Body of ``POST /configurations/templates``."""

    organization_id: UUID
    project_id: UUID | None = None
    template_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    configuration_type: ConfigurationType
    content: str = Field(min_length=1)
    variables_schema: dict[str, Any] = Field(default_factory=dict)


class ConfigurationTemplateUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/templates/{id}``."""

    template_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    configuration_type: ConfigurationType
    content: str = Field(min_length=1)
    variables_schema: dict[str, Any] = Field(default_factory=dict)


class ConfigurationTemplateResponse(BaseModel):
    """One reusable configuration template."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    template_name: str
    description: str | None
    configuration_type: ConfigurationType
    content: str
    variables_schema: dict[str, Any]


__all__ = [
    "ConfigurationTemplateCreateRequest",
    "ConfigurationTemplateResponse",
    "ConfigurationTemplateUpdateRequest",
]
