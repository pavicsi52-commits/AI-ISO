"""Response schema for ``GET /monitoring/statistics``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MonitoringStatisticsResponse(BaseModel):
    """One organization's cached monitoring analytics rollup."""

    total_targets: int
    total_metrics_collected: int
    average_availability_percentage: float
    average_health_score: float
    sla_compliance_percentage: float
    slo_compliance_percentage: float
    top_threshold_breaches: dict[str, Any]
    trend_data: dict[str, Any]
    computed_at: datetime


__all__ = ["MonitoringStatisticsResponse"]
