"""``alert_statistics`` table -- one organization's cached analytics
rollup. Per docs/045's own "ANALYTICS" "Collect" list: Alert Volume,
Alert Frequency, Top Alert Sources, Top Rules, Noise Ratio,
Suppression Rate, Resolution Time, MTTA, MTTR, Escalation Statistics.
Computed on demand and cached, the same "cached, not live" shape
``services/monitoring-service``'s own ``MonitoringStatistics`` already
established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class AlertStatistics(BaseModel):
    """One organization's cached alerting analytics rollup."""

    __tablename__ = "alert_statistics"

    total_alerts: Mapped[int] = mapped_column(Integer, default=0)
    open_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    noise_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    suppression_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_resolution_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    mtta_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    mttr_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    top_sources: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    top_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    escalation_statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trend_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AlertStatistics"]
