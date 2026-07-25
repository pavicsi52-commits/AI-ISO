"""Response schemas for ``GET /inventory/statistics`` and
``GET /inventory/analytics``. Per docs/036 "ANALYTICS": Asset Count,
Asset Types, Health Distribution, Lifecycle Distribution, OS
Distribution, Vendor Distribution, Location Distribution, Relationship
Count, Discovery Statistics, Growth Trends.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class InventoryStatisticsResponse(BaseModel):
    """The current-state inventory rollup ("Asset Count" through
    "Relationship Count").
    """

    total_assets: int
    total_relationships: int
    type_distribution: dict[str, Any]
    health_distribution: dict[str, Any]
    lifecycle_distribution: dict[str, Any]
    os_distribution: dict[str, Any]
    vendor_distribution: dict[str, Any]
    location_distribution: dict[str, Any]
    computed_at: datetime


class InventoryAnalyticsResponse(InventoryStatisticsResponse):
    """The statistics rollup plus growth trend and discovery-source
    breakdowns ("Discovery Statistics", "Growth Trends").
    """

    discovery_source_distribution: dict[str, Any]
    assets_added_last_30_days: int


__all__ = ["InventoryAnalyticsResponse", "InventoryStatisticsResponse"]
