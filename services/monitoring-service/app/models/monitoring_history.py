"""``monitoring_history`` table -- one lightweight, per-target
historical health snapshot row, distinct from the full
``monitoring_health``/``monitoring_metric_series`` rows so trend
queries ("Availability Trends"/"Failure Trends") can scan a small,
purpose-built table instead of re-aggregating the full result set on
every read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.enums.health_status import HealthStatus
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class MonitoringHistory(BaseModel):
    """One lightweight, per-target historical health snapshot."""

    __tablename__ = "monitoring_history"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[HealthStatus] = mapped_column(String(16), index=True)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["MonitoringHistory"]
