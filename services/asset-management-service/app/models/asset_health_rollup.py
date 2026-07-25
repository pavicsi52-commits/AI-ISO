"""``asset_health_rollups`` table. Per docs/038 "HEALTH MANAGEMENT"
"Aggregate": Monitoring Status, Validation Status, Discovery Status,
Automation Status, Incident Count, Performance Indicators,
Availability, Health Score, Health Trends. A cached, periodically
recomputed rollup rather than a live aggregation on every request --
the same "cached, not live" shape ``inventory-service``'s own
``inventory_statistics`` established; :attr:`health_trend` embeds a
short rolling series of past scores since docs/038 names no separate
trend-history table. The four *_status fields are free-text (docs/038
names them without enumerating values, unlike e.g. "ASSET STATUS").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetHealthRollup(BaseModel):
    """One managed asset's current cached operational-health rollup."""

    __tablename__ = "asset_health_rollups"
    __table_args__ = (
        UniqueConstraint("managed_asset_id", name="uq_asset_health_rollup_managed_asset"),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_status: Mapped[str] = mapped_column(String(32), default="unknown")
    validation_status: Mapped[str] = mapped_column(String(32), default="unknown")
    discovery_status: Mapped[str] = mapped_column(String(32), default="unknown")
    automation_status: Mapped[str] = mapped_column(String(32), default="unknown")
    incident_count: Mapped[int] = mapped_column(Integer, default=0)
    performance_indicators: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    availability_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), default=None)
    health_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    health_trend: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetHealthRollup"]
