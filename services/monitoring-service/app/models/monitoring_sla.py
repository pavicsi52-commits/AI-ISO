"""``monitoring_sla`` table -- one Service Level Agreement's own
tracked objective over a period ("SLA / SLO" "Track": Availability
SLA, Performance SLA, Compliance Percentage). ``shared_core.monitoring
.sla``'s own ``SlaReport``/``AvailabilityTracker`` are explicitly
in-process-only and reset on restart (their own module docstring:
"must not create business/persistence tables") -- this table is the
real, durable record that framework deliberately leaves for a real
service to own.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ComplianceStatus, SLAType


class MonitoringSLA(BaseModel):
    """One Service Level Agreement's own tracked objective over a period."""

    __tablename__ = "monitoring_sla"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    sla_type: Mapped[SLAType] = mapped_column(String(16), index=True)
    objective_percentage: Mapped[float] = mapped_column(Float)
    actual_percentage: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[ComplianceStatus] = mapped_column(
        String(16), default=ComplianceStatus.COMPLIANT, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["MonitoringSLA"]
