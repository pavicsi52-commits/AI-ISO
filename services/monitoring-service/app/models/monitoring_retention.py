"""``monitoring_retention`` table -- a retention/downsampling policy
("TIME SERIES" "Support": Retention Policies, Downsampling,
Compression). ``metric_type`` is nullable -- a ``None`` row is the
organization's own default policy, applied to any metric type with no
more specific policy of its own.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AggregationFunction, MetricType


class MonitoringRetention(BaseModel):
    """A retention/downsampling policy, optionally scoped to one metric type."""

    __tablename__ = "monitoring_retention"

    metric_type: Mapped[MetricType | None] = mapped_column(String(24), default=None, index=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    downsampling_function: Mapped[AggregationFunction | None] = mapped_column(
        String(8), default=None
    )
    downsampling_interval_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["MonitoringRetention"]
