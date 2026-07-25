"""``inventory_statistics`` table -- a cached analytics rollup for one
organization. Per docs/036 "ANALYTICS": Asset Count, Asset Types,
Health Distribution, Lifecycle Distribution, OS Distribution, Vendor
Distribution, Location Distribution, Relationship Count, Discovery
Statistics, Growth Trends. Recomputed periodically rather than
aggregated live on every request, the same "cached, not live" shape
``services/project-service``'s own ``project_statistics`` established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class InventoryStatistics(BaseModel):
    """One organization's cached inventory analytics snapshot."""

    __tablename__ = "inventory_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_inventory_statistics_org"),)

    total_assets: Mapped[int] = mapped_column(Integer, default=0)
    total_relationships: Mapped[int] = mapped_column(Integer, default=0)
    type_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    health_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lifecycle_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    os_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    vendor_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    location_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["InventoryStatistics"]
