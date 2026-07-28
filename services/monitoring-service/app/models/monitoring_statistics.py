"""``monitoring_statistics`` table -- one organization's cached
analytics rollup. Per docs/044's own "ANALYTICS" "Collect" list:
Metric Trends, Capacity Trends, Availability Trends, Failure Trends,
Resource Utilization, Growth Analysis, Forecasting Inputs. Computed on
demand and cached, the same "cached, not live" shape
``services/validation-service``'s own ``ValidationStatisticsService``
already established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class MonitoringStatistics(BaseModel):
    """One organization's cached monitoring analytics rollup."""

    __tablename__ = "monitoring_statistics"

    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    total_metrics_collected: Mapped[int] = mapped_column(Integer, default=0)
    average_availability_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    average_health_score: Mapped[float] = mapped_column(Float, default=0.0)
    sla_compliance_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    slo_compliance_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    top_threshold_breaches: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trend_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["MonitoringStatistics"]
