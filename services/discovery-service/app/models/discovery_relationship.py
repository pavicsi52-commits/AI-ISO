"""``discovery_relationships`` table -- one detected relationship edge
between two discovered assets, prior to (or pending) synchronization
into the Inventory Service and Neo4j.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DiscoveryRelationshipType


class DiscoveryRelationship(BaseModel):
    """One relationship edge detected between two discovered assets."""

    __tablename__ = "discovery_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_discovery_asset_id",
            "target_discovery_asset_id",
            "relationship_type",
            name="uq_discovery_relationship_edge",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    source_discovery_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_assets.id", ondelete="CASCADE"), index=True
    )
    target_discovery_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_assets.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[DiscoveryRelationshipType] = mapped_column(String(32), index=True)
    synced_to_inventory: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["DiscoveryRelationship"]
