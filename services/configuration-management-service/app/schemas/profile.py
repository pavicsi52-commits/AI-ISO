"""Request/response schemas for ``/configurations``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ConfigurationType, EnvironmentType, ProfileStatus


class ConfigurationProfileCreateRequest(BaseModel):
    """Body of ``POST /configurations``."""

    organization_id: UUID
    project_id: UUID | None = None
    profile_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    environment: EnvironmentType
    owner_id: UUID | None = None
    configuration_type: ConfigurationType
    target_assets: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfigurationProfileUpdateRequest(BaseModel):
    """Body of ``PUT /configurations/{id}``."""

    profile_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    status: ProfileStatus = ProfileStatus.DRAFT
    environment: EnvironmentType
    owner_id: UUID | None = None
    configuration_type: ConfigurationType
    target_assets: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfigurationProfilePatchRequest(BaseModel):
    """Body of ``PATCH /configurations/{id}`` -- every field optional."""

    profile_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    status: ProfileStatus | None = None
    environment: EnvironmentType | None = None
    owner_id: UUID | None = None
    configuration_type: ConfigurationType | None = None
    target_assets: list[str] | None = None
    variables: dict[str, Any] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ConfigurationProfileResponse(BaseModel):
    """One configuration profile, in full -- per docs/039 "CONFIGURATION
    PROFILE MODEL".
    """

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    profile_name: str
    description: str | None
    profile_version: str
    status: ProfileStatus
    environment: EnvironmentType
    owner_id: UUID | None
    configuration_type: ConfigurationType
    target_assets: list[str]
    variables: dict[str, Any]
    tags: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ConfigurationProfileCreateRequest",
    "ConfigurationProfilePatchRequest",
    "ConfigurationProfileResponse",
    "ConfigurationProfileUpdateRequest",
]
