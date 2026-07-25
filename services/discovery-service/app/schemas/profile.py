"""Request/response schemas for ``/discovery/profiles``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProfileType, ProtocolType


class DiscoveryProfileCreateRequest(BaseModel):
    """Body of ``POST /discovery/profiles``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    profile_type: ProfileType = ProfileType.CUSTOM
    protocols: list[ProtocolType] = Field(default_factory=list)
    default_ports: dict[str, int] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1)
    concurrency_limit: int = Field(default=10, ge=1)


class DiscoveryProfileUpdateRequest(BaseModel):
    """Body of ``PUT /discovery/profiles/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    profile_type: ProfileType = ProfileType.CUSTOM
    protocols: list[ProtocolType] = Field(default_factory=list)
    default_ports: dict[str, int] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1)
    concurrency_limit: int = Field(default=10, ge=1)


class DiscoveryProfileResponse(BaseModel):
    """One reusable discovery scan profile."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    profile_type: ProfileType
    protocols: list[str]
    default_ports: dict[str, Any]
    timeout_seconds: int
    concurrency_limit: int
    is_system: bool


__all__ = [
    "DiscoveryProfileCreateRequest",
    "DiscoveryProfileResponse",
    "DiscoveryProfileUpdateRequest",
]
