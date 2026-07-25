"""Request/response schemas for configuration environments."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import EnvironmentType


class ConfigurationEnvironmentCreateRequest(BaseModel):
    """Body of ``POST /configurations/environments``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    environment_type: EnvironmentType
    description: str | None = Field(default=None, max_length=2048)


class ConfigurationEnvironmentUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/environments/{id}``."""

    environment_type: EnvironmentType
    description: str | None = Field(default=None, max_length=2048)


class ConfigurationEnvironmentResponse(BaseModel):
    """One environment definition an organization tracks profiles against."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    environment_type: EnvironmentType
    description: str | None


__all__ = [
    "ConfigurationEnvironmentCreateRequest",
    "ConfigurationEnvironmentResponse",
    "ConfigurationEnvironmentUpdateRequest",
]
