"""``monitoring_availability`` table -- one uptime/downtime/maintenance
interval for a target ("Track": Uptime, Downtime, Maintenance Windows,
Outages). ``ended_at`` is nullable -- an ongoing interval (the target's
own *current* status) has no end yet; ``duration_seconds`` is computed
and filled in only once the interval closes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AvailabilityStatus


class MonitoringAvailability(BaseModel):
    """One uptime/downtime/maintenance interval for a target."""

    __tablename__ = "monitoring_availability"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[AvailabilityStatus] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)


__all__ = ["MonitoringAvailability"]
