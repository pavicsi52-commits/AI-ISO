"""``monitoring_metric_series`` table -- one measured data point ("High-
frequency Metrics"). The potentially high-volume time-series table this
whole service exists to populate; ``tags`` carries dimensional labels
(e.g. ``{"mount": "/var"}`` for a filesystem metric) the same way a
Prometheus label set would, without needing a separate column per
possible dimension.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class MonitoringMetricSeries(BaseModel):
    """One measured data point for a metric against a target."""

    __tablename__ = "monitoring_metric_series"

    metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_metrics.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[float] = mapped_column(Float)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["MonitoringMetricSeries"]
