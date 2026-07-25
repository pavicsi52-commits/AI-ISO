"""Request/response schemas for ``/inventory/groups``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import GroupType


class AssetGroupCreateRequest(BaseModel):
    """Body of ``POST /inventory/groups``."""

    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    group_type: GroupType = GroupType.STATIC
    rule: dict[str, Any] = Field(default_factory=dict)
    member_asset_ids: list[UUID] = Field(default_factory=list)


class AssetGroupResponse(BaseModel):
    """One asset group."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    group_type: GroupType
    rule: dict[str, Any]
    member_asset_ids: list[str]


__all__ = ["AssetGroupCreateRequest", "AssetGroupResponse"]
