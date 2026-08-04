"""``incident_slas`` and ``incident_escalations``.

The clocks an incident is measured against, and what fires when one runs
out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EscalationStatus, EscalationTrigger, SlaKind, SlaStatus


class IncidentSla(BaseModel):
    """``incident_slas`` -- one clock (response, acknowledgement, ...)."""

    __tablename__ = "incident_slas"
    __table_args__ = (
        Index("ix_incident_sla_incident", "organization_id", "incident_id", "kind"),
        Index("ix_incident_sla_status", "organization_id", "status"),
        Index("ix_incident_sla_due", "organization_id", "due_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[SlaKind] = mapped_column(String(32), index=True)
    status: Mapped[SlaStatus] = mapped_column(String(32), default=SlaStatus.PENDING, index=True)

    target_minutes: Mapped[int] = mapped_column(Integer)
    is_24x7: Mapped[bool] = mapped_column(Boolean, default=True)
    """Whether this clock runs around the clock or only during business
    hours. A business-hours SLA's ``due_at`` is computed by
    ``app/sla/engine.py`` walking forward across the configured
    calendar, skipping the hours the clock does not run -- never by
    adding ``target_minutes`` straight onto ``started_at``, which would
    silently convert a business-hours SLA into a 24x7 one."""

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    paused_seconds_total: Mapped[float] = mapped_column(Float, default=0.0)
    """Accumulated pause time, carried across every pause/resume cycle.
    Subtracted from elapsed time so a clock paused waiting on a vendor
    does not count that wait as time this organization failed to meet
    its own SLA."""

    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    warning_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    pause_reason: Mapped[str | None] = mapped_column(Text, default=None)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IncidentEscalation(BaseModel):
    """``incident_escalations`` -- one escalation, fired or pending."""

    __tablename__ = "incident_escalations"
    __table_args__ = (
        Index("ix_incident_escalation_incident", "organization_id", "incident_id"),
        Index("ix_incident_escalation_status", "organization_id", "status"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    sla_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incident_slas.id", ondelete="SET NULL"), default=None
    )
    trigger: Mapped[EscalationTrigger] = mapped_column(String(32), index=True)
    status: Mapped[EscalationStatus] = mapped_column(
        String(32), default=EscalationStatus.PENDING, index=True
    )

    level: Mapped[int] = mapped_column(Integer, default=1)
    """Which rung of the escalation ladder this is. A policy with three
    levels and an incident already at level 2 must escalate to 3 next,
    never back to 1 -- the level is what lets the engine tell those
    apart without re-deriving it from the trigger history."""

    escalate_to_id: Mapped[str | None] = mapped_column(String(255), default=None)
    escalate_to_role: Mapped[str | None] = mapped_column(String(128), default=None)
    reason: Mapped[str] = mapped_column(Text)

    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["IncidentEscalation", "IncidentSla"]
