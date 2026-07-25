"""Request/response schemas for ``/permissions``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.security.rbac import PermissionScope

from app.models.enums import PermissionAction, PermissionStatus, ResourceType


class PermissionCreateRequest(BaseModel):
    """Body of ``POST /permissions``."""

    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    category: str | None = None
    resource: ResourceType
    action: PermissionAction
    scope: PermissionScope = PermissionScope.GLOBAL
    permission_group_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionUpdateRequest(BaseModel):
    """Body of ``PUT /permissions/{id}``."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    category: str | None = None
    status: PermissionStatus = PermissionStatus.ACTIVE
    permission_group_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionResponse(BaseModel):
    """One permission, in full."""

    id: UUID
    name: str
    code: str
    description: str | None
    category: str | None
    resource: ResourceType
    action: PermissionAction
    scope: PermissionScope
    status: PermissionStatus
    version: int
    permission_group_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["PermissionCreateRequest", "PermissionResponse", "PermissionUpdateRequest"]
