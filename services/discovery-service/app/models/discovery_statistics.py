"""``discovery_statistics`` table -- one cached rollup row per
organization, the same "cached, not live" shape
``services/inventory-service``'s own ``inventory_statistics`` established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


class DiscoveryStatistics(BaseModel):
    """One organization's cached discovery analytics snapshot."""

    __tablename__ = "discovery_statistics"

    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    total_assets_discovered: Mapped[int] = mapped_column(Integer, default=0)
    total_relationships_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_by_mode: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assets_by_classification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failures_by_reason: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_discovery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["DiscoveryStatistics"]
