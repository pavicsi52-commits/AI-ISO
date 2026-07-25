"""``asset_relationships`` table -- Postgres is the authoritative,
queryable source of truth for one relationship edge between two assets;
`app/topology/` mirrors every create/delete here into Neo4j as a graph
edge, so traversal-heavy operations ("Relationship Traversal", "Impact
Analysis") run against the graph while ordinary CRUD/audit/listing
stays in the same relational store every other AI-IOS entity uses.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RelationshipType


class AssetRelationship(BaseModel):
    """One directed relationship edge between two assets."""

    __tablename__ = "asset_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relationship_type",
            name="uq_asset_relationship_edge",
        ),
    )

    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(String(32), index=True)
    custom_label: Mapped[str | None] = mapped_column(String(128), default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["AssetRelationship"]
