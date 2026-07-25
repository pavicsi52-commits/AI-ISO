"""Response schema for ``GET /assets/{id}/health``. Named
``asset_health`` (not ``health``) to avoid colliding with
``app/schemas/health.py``'s own service health/readiness/liveness shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AssetHealthRollupResponse(BaseModel):
    """One managed asset's current cached operational-health rollup."""

    id: UUID
    managed_asset_id: UUID
    monitoring_status: str
    validation_status: str
    discovery_status: str
    automation_status: str
    incident_count: int
    performance_indicators: dict[str, Any]
    availability_percent: float | None
    health_score: float
    health_trend: list[dict[str, Any]]
    computed_at: datetime


__all__ = ["AssetHealthRollupResponse"]
