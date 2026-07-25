"""Request/response schemas for configuration baselines."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import BaselineType


class ConfigurationBaselineCreateRequest(BaseModel):
    """Body of ``POST /configurations/baselines``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_id: UUID | None = None
    baseline_type: BaselineType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    content: dict[str, Any] = Field(default_factory=dict)


class ConfigurationBaselineUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/baselines/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    content: dict[str, Any] = Field(default_factory=dict)


class ConfigurationBaselineResponse(BaseModel):
    """One golden/compliance/security/performance/vendor/custom baseline."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_id: UUID | None
    baseline_type: BaselineType
    name: str
    description: str | None
    baseline_version: str
    content: dict[str, Any]


__all__ = [
    "ConfigurationBaselineCreateRequest",
    "ConfigurationBaselineResponse",
    "ConfigurationBaselineUpdateRequest",
]
