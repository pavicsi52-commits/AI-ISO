"""Request/response schemas for ``/inventory/relationships``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RelationshipType


class AssetRelationshipCreateRequest(BaseModel):
    """Body of ``POST /inventory/relationships``."""

    organization_id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    relationship_type: RelationshipType
    custom_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetRelationshipResponse(BaseModel):
    """One directed relationship edge between two assets."""

    id: UUID
    organization_id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    relationship_type: RelationshipType
    custom_label: str | None
    metadata: dict[str, Any]


__all__ = ["AssetRelationshipCreateRequest", "AssetRelationshipResponse"]
