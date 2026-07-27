"""``validation_statistics`` table -- one organization's cached
analytics rollup. Per docs/043's own "ANALYTICS" "Collect" list:
Execution Count, Pass Rate, Failure Rate, Validation Duration, Top
Failures, Trend Analysis, Asset Health Trends, Compliance Trends.
Computed on demand and cached, the same "cached, not live" shape
``services/workflow-runtime-service``'s own
``WorkflowStatisticsService`` already established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class ValidationStatistics(BaseModel):
    """One organization's cached validation analytics rollup."""

    __tablename__ = "validation_statistics"

    total_profiles: Mapped[int] = mapped_column(Integer, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    top_failures: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trend_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    asset_health_trends: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance_trends: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ValidationStatistics"]
