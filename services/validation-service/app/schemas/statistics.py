"""Response schema for ``GET /validation/statistics``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ValidationStatisticsResponse(BaseModel):
    """One organization's cached validation analytics rollup."""

    total_profiles: int
    total_executions: int
    pass_rate: float
    failure_rate: float
    average_duration_seconds: float
    top_failures: dict[str, Any]
    trend_data: dict[str, Any]
    asset_health_trends: dict[str, Any]
    compliance_trends: dict[str, Any]
    computed_at: datetime


__all__ = ["ValidationStatisticsResponse"]
