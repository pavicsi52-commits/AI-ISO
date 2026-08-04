"""``incident_timelines``, ``incident_worklogs``, ``incident_assignments``.

What happened, what work was done about it, and who has held it. Three
separate tables rather than one, because they answer three different
questions an incident review asks: *what is the sequence of events*,
*what effort went in*, and *who was accountable when* -- and merging
them would force every worklog entry to pretend to be a timeline event
or vice versa.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssignmentMethod, TimelineEventKind, WorklogKind


class IncidentTimeline(BaseModel):
    """``incident_timelines`` -- the append-only sequence of what happened.

    Never updated, never deleted. A timeline entry misdescribing what
    happened is corrected by adding a new entry that says so, the same
    way a postmortem corrects the record -- editing history out from
    under a bridge call full of people who read it live is worse than
    leaving the mistake visible.
    """

    __tablename__ = "incident_timelines"
    __table_args__ = (
        Index("ix_incident_timeline_incident", "organization_id", "incident_id", "occurred_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[TimelineEventKind] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(255), default=None)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IncidentWorklog(BaseModel):
    """``incident_worklogs`` -- effort actually spent, by whom."""

    __tablename__ = "incident_worklogs"
    __table_args__ = (
        Index("ix_incident_worklog_incident", "organization_id", "incident_id"),
        Index("ix_incident_worklog_author", "organization_id", "author_id"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[WorklogKind] = mapped_column(String(32), default=WorklogKind.OTHER)
    author_id: Mapped[str | None] = mapped_column(String(255), default=None)
    note: Mapped[str] = mapped_column(Text)
    minutes_spent: Mapped[int | None] = mapped_column(default=None)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IncidentAssignment(BaseModel):
    """``incident_assignments`` -- the history of who has held an incident.

    A row per handoff, not one mutable "current assignee" field. Without
    this, "who had it when it breached SLA" is unanswerable the moment
    the incident moves on -- and that is precisely the question a
    post-incident review asks first.
    """

    __tablename__ = "incident_assignments"
    __table_args__ = (
        Index("ix_incident_assignment_incident", "organization_id", "incident_id", "assigned_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    assignee_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    assignee_team: Mapped[str | None] = mapped_column(String(255), default=None)
    method: Mapped[AssignmentMethod] = mapped_column(String(32), default=AssignmentMethod.MANUAL)
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["IncidentAssignment", "IncidentTimeline", "IncidentWorklog"]
