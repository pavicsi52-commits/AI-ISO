"""Response schema for ``GET /discovery/statistics``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DiscoveryStatisticsResponse(BaseModel):
    """One organization's cached discovery analytics snapshot."""

    total_jobs: int
    total_assets_discovered: int
    total_relationships_discovered: int
    jobs_by_mode: dict[str, Any]
    assets_by_classification: dict[str, Any]
    failures_by_reason: dict[str, Any]
    last_discovery_at: datetime | None
    computed_at: datetime


__all__ = ["DiscoveryStatisticsResponse"]
