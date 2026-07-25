"""``asset_statistics`` table -- a cached analytics rollup for one
organization. Per docs/038 "ANALYTICS" "Collect": Asset Growth,
Operational Health, Maintenance Trends, Compliance Trends, Risk
Trends, Cost Trends, Vendor Performance, Lifecycle Distribution.
Recomputed periodically rather than aggregated live on every request,
matching ``inventory-service``'s own ``inventory_statistics``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetStatistics(BaseModel):
    """One organization's cached asset-management analytics snapshot."""

    __tablename__ = "asset_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_asset_statistics_org"),)

    total_managed_assets: Mapped[int] = mapped_column(Integer, default=0)
    asset_growth: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    criticality_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lifecycle_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cost_trends: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    maintenance_trends: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    vendor_performance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetStatistics"]
