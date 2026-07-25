"""Response schema for ``GET /assets/analytics``. Per docs/038
"ANALYTICS" "Collect": Asset Growth, Operational Health, Maintenance
Trends, Compliance Trends, Risk Trends, Cost Trends, Vendor
Performance, Lifecycle Distribution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AssetStatisticsResponse(BaseModel):
    """The current-state asset-management analytics rollup."""

    total_managed_assets: int
    asset_growth: dict[str, Any]
    status_distribution: dict[str, Any]
    criticality_distribution: dict[str, Any]
    lifecycle_distribution: dict[str, Any]
    compliance_distribution: dict[str, Any]
    risk_distribution: dict[str, Any]
    cost_trends: dict[str, Any]
    maintenance_trends: dict[str, Any]
    vendor_performance: dict[str, Any]
    computed_at: datetime


__all__ = ["AssetStatisticsResponse"]
