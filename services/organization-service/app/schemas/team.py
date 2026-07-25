"""Request/response schemas for ``/organizations/{id}/teams`` and ``/teams/{id}``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    """Body of ``POST /organizations/{id}/teams``."""

    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    description: str | None = None
    department_id: UUID | None = None
    business_unit_id: UUID | None = None
    team_lead_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamUpdateRequest(BaseModel):
    """Body of ``PUT /teams/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    department_id: UUID | None = None
    business_unit_id: UUID | None = None
    team_lead_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamResponse(BaseModel):
    """One team, in full."""

    id: UUID
    organization_id: UUID
    name: str
    code: str
    description: str | None
    department_id: UUID | None
    business_unit_id: UUID | None
    team_lead_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["TeamCreateRequest", "TeamResponse", "TeamUpdateRequest"]
