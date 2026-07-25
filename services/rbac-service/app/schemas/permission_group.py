"""Request/response schemas for ``/permission-groups``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PermissionGroupCategory


class PermissionGroupCreateRequest(BaseModel):
    """Body of ``POST /permission-groups``."""

    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    category: PermissionGroupCategory = PermissionGroupCategory.CUSTOM
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionGroupResponse(BaseModel):
    """One permission group, in full."""

    id: UUID
    name: str
    code: str
    description: str | None
    category: PermissionGroupCategory
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["PermissionGroupCreateRequest", "PermissionGroupResponse"]
