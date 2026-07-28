"""``monitoring_slo`` table -- one Service Level Objective's own tracked
target over a period ("SLA / SLO" "Track": Latency SLO, Error Budget,
Objective Violations). ``error_budget_remaining_percentage`` tracks how
much of the allowed non-compliant window remains before the objective
is formally violated for the period.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ComplianceStatus, SLOType


class MonitoringSLO(BaseModel):
    """One Service Level Objective's own tracked target over a period."""

    __tablename__ = "monitoring_slo"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="CASCADE"), index=True
    )
    slo_type: Mapped[SLOType] = mapped_column(String(16), index=True)
    objective_value: Mapped[float] = mapped_column(Float)
    actual_value: Mapped[float | None] = mapped_column(Float, default=None)
    error_budget_remaining_percentage: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[ComplianceStatus] = mapped_column(
        String(16), default=ComplianceStatus.COMPLIANT, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["MonitoringSLO"]
