"""``monitoring_health`` table -- one health-check result snapshot.

``status`` reuses :class:`shared_core.enums.health_status.HealthStatus`
directly (the platform-wide "worst-case status rollup" vocabulary
every service's own ``/readiness`` endpoint already uses) rather than
introducing a second, parallel status enum for the identical concept.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.enums.health_status import HealthStatus
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import HealthCheckType


class MonitoringHealth(BaseModel):
    """One health-check result snapshot for a target."""

    __tablename__ = "monitoring_health"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    check_type: Mapped[HealthCheckType] = mapped_column(String(24), index=True)
    status: Mapped[HealthStatus] = mapped_column(
        String(16), default=HealthStatus.UNKNOWN, index=True
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["MonitoringHealth"]
