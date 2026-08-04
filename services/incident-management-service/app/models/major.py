"""``incident_major_events`` and ``incident_war_rooms``.

Declaring an incident major and standing up the coordination structure
that follows. A war room participant table sits alongside the two docs/
052 names explicitly, because "who was in the room" is exactly the
question a major-incident postmortem asks and there is nowhere else in
the schema that answers it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import WarRoomRole, WarRoomStatus


class MajorIncidentEvent(BaseModel):
    """``incident_major_events`` -- the declaration and its closure.

    Declaration is deliberately a separate table from :class:`Incident`,
    not a boolean flag alone: a major incident carries a commander, a
    communication cadence, and an executive summary that an ordinary
    incident does not, and giving those fields a home only on the rows
    that need them keeps every ordinary incident's row from carrying
    nulls for machinery it will never use.
    """

    __tablename__ = "incident_major_events"
    __table_args__ = (Index("ix_major_incident_incident", "organization_id", "incident_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    declared_by: Mapped[str | None] = mapped_column(String(255), default=None)
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    declaration_reason: Mapped[str] = mapped_column(Text)

    incident_commander_id: Mapped[str | None] = mapped_column(String(255), default=None)
    communication_lead_id: Mapped[str | None] = mapped_column(String(255), default=None)
    technical_lead_id: Mapped[str | None] = mapped_column(String(255), default=None)
    business_lead_id: Mapped[str | None] = mapped_column(String(255), default=None)

    status_update_interval_minutes: Mapped[int] = mapped_column(default=30)
    last_status_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    executive_summary: Mapped[str | None] = mapped_column(Text, default=None)

    stood_down_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    stood_down_by: Mapped[str | None] = mapped_column(String(255), default=None)
    closure_approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    closure_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    stakeholder_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WarRoom(BaseModel):
    """``incident_war_rooms`` -- the coordination space for one incident."""

    __tablename__ = "incident_war_rooms"
    __table_args__ = (Index("ix_war_room_incident", "organization_id", "incident_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    major_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incident_major_events.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[WarRoomStatus] = mapped_column(
        String(32), default=WarRoomStatus.OPEN, index=True
    )

    opened_by: Mapped[str | None] = mapped_column(String(255), default=None)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    shared_notes: Mapped[str | None] = mapped_column(Text, default=None)
    shared_artifacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Links and references participants attached during the incident --
    dashboards, log queries, dumps -- not the files themselves. Evidence
    storage belongs to the service that owns each artifact; duplicating
    it here would create a second copy nobody keeps in sync."""

    recording_reference: Mapped[str | None] = mapped_column(String(1_024), default=None)
    automation_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    workflow_executions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class WarRoomParticipant(BaseModel):
    """One person in one war room, with the role they held.

    Enforces at most one holder per :data:`~app.models.enums
    .SINGLETON_WAR_ROOM_ROLES` role -- see
    ``app/major_incidents/engine.py`` for why that is the whole point of
    naming roles rather than leaving "who is doing what" to the shared
    notes.
    """

    __tablename__ = "incident_war_room_participants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "war_room_id",
            "participant_id",
            "role",
            name="uq_war_room_participant",
        ),
        Index("ix_war_room_participant_room", "organization_id", "war_room_id"),
    )

    war_room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incident_war_rooms.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[WarRoomRole] = mapped_column(String(32), default=WarRoomRole.PARTICIPANT)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["MajorIncidentEvent", "WarRoom", "WarRoomParticipant"]
