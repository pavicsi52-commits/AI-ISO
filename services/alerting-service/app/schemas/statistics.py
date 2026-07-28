"""Response schema for ``GET /alert-statistics``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AlertStatisticsResponse(BaseModel):
    """One organization's cached alerting analytics rollup."""

    total_alerts: int
    open_alert_count: int
    noise_ratio: float
    suppression_rate: float
    average_resolution_seconds: float
    mtta_seconds: float
    mttr_seconds: float
    top_sources: dict[str, Any]
    top_rules: dict[str, Any]
    escalation_statistics: dict[str, Any]
    trend_data: dict[str, Any]
    computed_at: datetime


__all__ = ["AlertStatisticsResponse"]
