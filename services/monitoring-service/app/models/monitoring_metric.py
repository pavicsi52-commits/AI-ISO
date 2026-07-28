"""``monitoring_metrics`` table -- a standalone, reusable definition of
one thing to measure ("Reusable Check Libraries"-equivalent for
metrics), referenced by id from any number of
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
data points. A metric definition only names *what* is measured and
*how* (via ``collector_id``); the actual measured values live in the
separate, potentially high-volume time-series table.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MetricType


class MonitoringMetric(BaseModel):
    """A standalone, reusable definition of one thing to measure."""

    __tablename__ = "monitoring_metrics"

    collector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_collectors.id", ondelete="SET NULL"), default=None, index=True
    )
    metric_type: Mapped[MetricType] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    unit: Mapped[str | None] = mapped_column(String(32), default=None)


__all__ = ["MonitoringMetric"]
