"""Request/response schemas for ``/roles``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RoleStatus, RoleType


class RoleCreateRequest(BaseModel):
    """Body of ``POST /roles``."""

    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    role_type: RoleType = RoleType.CUSTOM
    parent_role_id: UUID | None = None
    priority: int = 0
    project_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoleUpdateRequest(BaseModel):
    """Body of ``PUT /roles/{id}``."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    status: RoleStatus = RoleStatus.ACTIVE
    parent_role_id: UUID | None = None
    priority: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoleResponse(BaseModel):
    """One role, in full."""

    id: UUID
    name: str
    code: str
    description: str | None
    role_type: RoleType
    status: RoleStatus
    parent_role_id: UUID | None
    is_system: bool
    priority: int
    organization_id: UUID
    project_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["RoleCreateRequest", "RoleResponse", "RoleUpdateRequest"]
