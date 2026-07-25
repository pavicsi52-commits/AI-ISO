"""``asset_topology_cache`` table -- a cached snapshot of a Neo4j
topology query result, keyed by asset and query kind. Per docs/036
"PERFORMANCE": "Neo4j Batch Updates", "Optimized Search" -- repeated
graph traversals (dependency graph, impact analysis) for the same
asset are expensive to recompute on every request, so the topology
service persists the last-computed result here with a short TTL rather
than always round-tripping to Neo4j.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetTopologyCacheEntry(BaseModel):
    """One cached topology query result for an asset."""

    __tablename__ = "asset_topology_cache"
    __table_args__ = (
        UniqueConstraint("asset_id", "query_kind", name="uq_asset_topology_cache_entry"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AssetTopologyCacheEntry"]
