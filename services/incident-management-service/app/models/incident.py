"""``incidents`` and the organization-configurable lookup tables beside it.

The core record and the three catalogues docs/052 names alongside it:
categories, priorities, and statuses. The enums in
``app/models/enums.py`` fix the *platform's* vocabulary -- what every
built-in rule (SLA defaults, priority ordering, escalation policy)
reasons about; these tables let an organization describe and reorder
that vocabulary for its own dashboards without the enum becoming
customer data, the same split Prompt 050 established for
``PolicyCategoryRecord``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    IncidentCategory,
    IncidentPriority,
    IncidentSource,
    IncidentStatus,
    RiskLevel,
)


class IncidentCategoryRecord(BaseModel):
    """``incident_categories`` -- a named grouping an organization defines."""

    __tablename__ = "incident_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_incident_category_slug"),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[IncidentCategory] = mapped_column(
        String(64), default=IncidentCategory.CUSTOM, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class IncidentPriorityRecord(BaseModel):
    """``incident_priorities`` -- an organization's own SLA windows.

    Overrides :data:`~app.models.enums.DEFAULT_SLA_MINUTES` for one
    priority level. A row's absence is not an error -- the platform
    default applies -- so an organization only needs to write the levels
    it actually wants to change.
    """

    __tablename__ = "incident_priorities"
    __table_args__ = (UniqueConstraint("organization_id", "priority", name="uq_incident_priority"),)

    priority: Mapped[IncidentPriority] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    response_sla_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    acknowledgement_sla_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    resolution_sla_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    color: Mapped[str | None] = mapped_column(String(32), default=None)


class IncidentStatusRecord(BaseModel):
    """``incident_status`` -- display metadata for a lifecycle status.

    Never changes what the status *means* -- ``app/incidents/engine.py``
    owns the transition graph and nothing here can widen it -- only how
    it is labelled and coloured on a board.
    """

    __tablename__ = "incident_status"
    __table_args__ = (
        UniqueConstraint("organization_id", "status", name="uq_incident_status_record"),
    )

    status: Mapped[IncidentStatus] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    color: Mapped[str | None] = mapped_column(String(32), default=None)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Incident(BaseModel):
    """``incidents`` -- one operational incident."""

    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("organization_id", "reference", name="uq_incident_reference"),
        Index("ix_incident_org_status", "organization_id", "status"),
        Index("ix_incident_org_priority", "organization_id", "priority"),
        Index("ix_incident_org_created", "organization_id", "created_at"),
        Index("ix_incident_fingerprint", "organization_id", "fingerprint"),
        Index("ix_incident_assignee", "organization_id", "assignee_id"),
    )

    reference: Mapped[str] = mapped_column(String(64))
    """A human-quotable identifier -- ``INC-0042``. What gets said out
    loud on a bridge call, unlike a UUID."""

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    source: Mapped[IncidentSource] = mapped_column(String(64), default=IncidentSource.MANUAL)
    source_reference: Mapped[str | None] = mapped_column(String(512), default=None)
    """The upstream id this incident was raised from -- an alert id, a
    validation run id. What makes "why does this incident exist"
    checkable rather than merely asserted."""

    category: Mapped[IncidentCategory] = mapped_column(
        String(64), default=IncidentCategory.CUSTOM, index=True
    )
    priority: Mapped[IncidentPriority] = mapped_column(
        String(32), default=IncidentPriority.P3_MEDIUM, index=True
    )
    status: Mapped[IncidentStatus] = mapped_column(
        String(32), default=IncidentStatus.NEW, index=True
    )

    fingerprint: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    """Stable identity for "this same problem, recurring". Distinct
    monitoring firings for the same underlying condition correlate onto
    one open incident rather than opening a new one every polling
    interval -- see ``app/incidents/engine.py``."""

    assignee_id: Mapped[str | None] = mapped_column(String(255), default=None)
    assignee_team: Mapped[str | None] = mapped_column(String(255), default=None)
    assignment_method: Mapped[str | None] = mapped_column(String(32), default=None)

    risk_level: Mapped[RiskLevel] = mapped_column(String(32), default=RiskLevel.LOW)
    is_major: Mapped[bool] = mapped_column(default=False, index=True)
    major_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "incident_major_events.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_incident_major_incident",
        ),
        default=None,
    )
    """``use_alter=True``: ``incident_major_events.incident_id`` also
    points back at this table, and a genuine mutual foreign key between
    two tables has no valid ``CREATE TABLE`` order -- whichever table is
    created first would reference one that does not exist yet. Deferring
    this constraint to a post-create ``ALTER TABLE`` breaks the cycle."""

    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), default=None
    )
    """Set only when :attr:`status` is ``MERGED``. The absorbing
    incident's worklog and timeline are what remains authoritative;
    this incident's own history stays in place rather than being
    rewritten, so nothing that already cited it becomes wrong."""

    problem_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("problem_records.id", ondelete="SET NULL"), default=None
    )
    root_cause_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "incident_root_causes.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_incident_root_cause",
        ),
        default=None,
    )
    """``use_alter=True`` for the same reason as ``major_incident_id``:
    ``incident_root_causes.incident_id`` points back at this table."""

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    mtta_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    mttr_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    """Computed once at close, not derived at read time. An incident
    reopened after closure gets a fresh MTTR calculation rather than one
    that silently drifts every time somebody re-reads the row."""

    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = [
    "Incident",
    "IncidentCategoryRecord",
    "IncidentPriorityRecord",
    "IncidentStatusRecord",
]
