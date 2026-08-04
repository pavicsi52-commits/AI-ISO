"""Declaring an incident major, and running the war room around it.

Two closely related concerns in one module because a major-incident
declaration and its war room are opened together in practice, and
keeping them in separate services would mean every caller has to
sequence two calls correctly instead of one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.incident_events import SOURCE_SERVICE, MajorIncidentDeclaredEvent
from app.models.enums import (
    SINGLETON_WAR_ROOM_ROLES,
    TERMINAL_INCIDENT_STATUSES,
    IncidentStatus,
    WarRoomRole,
    WarRoomStatus,
    incident_status_of,
    war_room_status_of,
)
from app.models.major import MajorIncidentEvent, WarRoom, WarRoomParticipant
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.incident import IncidentRepository
from app.repositories.major import (
    MajorIncidentRepository,
    WarRoomParticipantRepository,
    WarRoomRepository,
)
from app.types import EventPublisher

logger = get_logger("app.services.major_incident")

_CLOSEABLE_STATUSES = TERMINAL_INCIDENT_STATUSES | {IncidentStatus.RESOLVED}


class MajorIncidentService:
    """Major incident declaration, war rooms, and their participants."""

    def __init__(
        self,
        major_incidents: MajorIncidentRepository,
        war_rooms: WarRoomRepository,
        participants: WarRoomParticipantRepository,
        incidents: IncidentRepository,
        notifications: IncidentNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._major_incidents = major_incidents
        self._war_rooms = war_rooms
        self._participants = participants
        self._incidents = incidents
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def declare(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        reason: str,
        incident_commander_id: str | None = None,
        stakeholder_ids: list[str] | None = None,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> tuple[MajorIncidentEvent, WarRoom]:
        """Declare an incident major and open its war room.

        Raises:
            ConflictError: If this incident is already declared major.
        """
        moment = now or datetime.now(UTC)
        stored = await self._incidents.require_in_org(organization_id, incident_id)
        if await self._major_incidents.get_for_incident(organization_id, incident_id) is not None:
            raise ConflictError(f"{stored.reference} is already declared a major incident.")

        declaration = await self._major_incidents.create(
            MajorIncidentEvent(
                organization_id=organization_id,
                incident_id=incident_id,
                declared_by=str(actor_id) if actor_id else None,
                declared_at=moment,
                declaration_reason=reason,
                incident_commander_id=incident_commander_id,
                stakeholder_ids=list(stakeholder_ids or []),
                created_by=actor_id,
            )
        )

        stored.is_major = True
        stored.major_incident_id = declaration.id
        stored.updated_by = actor_id
        await self._incidents.update(stored)

        war_room = await self._war_rooms.create(
            WarRoom(
                organization_id=organization_id,
                incident_id=incident_id,
                major_incident_id=declaration.id,
                status=WarRoomStatus.OPEN,
                opened_by=str(actor_id) if actor_id else None,
                opened_at=moment,
                created_by=actor_id,
            )
        )

        if incident_commander_id:
            await self._participants.create(
                WarRoomParticipant(
                    organization_id=organization_id,
                    war_room_id=war_room.id,
                    participant_id=incident_commander_id,
                    role=WarRoomRole.INCIDENT_COMMANDER,
                    joined_at=moment,
                )
            )

        await self._publish_event(
            MajorIncidentDeclaredEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "incident_id": str(incident_id),
                    "major_incident_id": str(declaration.id),
                    "reason": reason,
                },
            )
        )
        for stakeholder_id in stakeholder_ids or []:
            await self._notifications.send_major_incident_declared(
                stakeholder_id,
                reference=stored.reference,
                title=stored.title,
                commander_id=incident_commander_id,
            )
        return declaration, war_room

    async def assign_role(
        self,
        organization_id: UUID,
        war_room_id: UUID,
        *,
        participant_id: str,
        role: WarRoomRole,
        now: datetime | None = None,
    ) -> WarRoomParticipant:
        """Add a participant to a war room, in a given role.

        Idempotent when *participant_id* already currently holds *role*:
        the existing row is returned rather than inserting a duplicate,
        which the ``(organization_id, war_room_id, participant_id,
        role)`` uniqueness constraint applies to every role, singleton
        or not, and would otherwise reject.

        Raises:
            ConflictError: If *role* is a singleton role
                (:data:`~app.models.enums.SINGLETON_WAR_ROOM_ROLES`)
                already held by someone else.
        """
        moment = now or datetime.now(UTC)
        await self._war_rooms.require_in_org(organization_id, war_room_id)

        if role in SINGLETON_WAR_ROOM_ROLES:
            holder = await self._participants.holder_of(organization_id, war_room_id, str(role))
            if holder is not None:
                if holder.participant_id != participant_id:
                    raise ConflictError(
                        f"{role!s} is already held by {holder.participant_id}. "
                        "Reassign it explicitly before assigning someone else."
                    )
                return holder
        else:
            current = await self._participants.list_current(organization_id, war_room_id)
            existing = next(
                (
                    one
                    for one in current
                    if one.participant_id == participant_id and one.role == str(role)
                ),
                None,
            )
            if existing is not None:
                return existing

        return await self._participants.create(
            WarRoomParticipant(
                organization_id=organization_id,
                war_room_id=war_room_id,
                participant_id=participant_id,
                role=role,
                joined_at=moment,
            )
        )

    async def leave(
        self,
        organization_id: UUID,
        war_room_id: UUID,
        *,
        participant_id: str,
        now: datetime | None = None,
    ) -> None:
        """Mark a participant as having left the war room."""
        current = [
            one
            for one in await self._participants.list_current(organization_id, war_room_id)
            if one.participant_id == participant_id
        ]
        moment = now or datetime.now(UTC)
        for one in current:
            one.left_at = moment
            await self._participants.update(one)

    async def add_shared_note(
        self, organization_id: UUID, war_room_id: UUID, *, note: str
    ) -> WarRoom:
        """Append to a war room's shared notes."""
        room = await self._war_rooms.require_in_org(organization_id, war_room_id)
        room.shared_notes = f"{room.shared_notes}\n{note}" if room.shared_notes else note
        return await self._war_rooms.update(room)

    async def stand_down(
        self,
        organization_id: UUID,
        war_room_id: UUID,
        *,
        stood_down_by: str | None = None,
        now: datetime | None = None,
    ) -> WarRoom:
        """Close a war room.

        Standing down a war room is independent of closing out the major
        incident declaration itself -- coordination can reasonably end
        before executive closure approval is granted, and conflating the
        two would force every war room to stay open past the point
        anyone is actually using it.

        Raises:
            ConflictError: If it is already closed.
        """
        room = await self._war_rooms.require_in_org(organization_id, war_room_id)
        if war_room_status_of(room.status) is WarRoomStatus.CLOSED:
            raise ConflictError(f"War room {war_room_id} is already closed.")
        room.status = WarRoomStatus.CLOSED
        room.closed_at = now or datetime.now(UTC)
        return await self._war_rooms.update(room)

    async def approve_closure(
        self,
        organization_id: UUID,
        major_incident_id: UUID,
        *,
        approved_by: str,
        now: datetime | None = None,
    ) -> MajorIncidentEvent:
        """Record executive approval to close out a major incident.

        Raises:
            ValidationError: If the underlying incident has not reached
                at least ``RESOLVED`` -- closure approval is for an
                incident that is actually over, not a way to
                fast-forward one that is not.
            ConflictError: If it was already stood down.
        """
        declaration = await self._major_incidents.require_in_org(organization_id, major_incident_id)
        if declaration.stood_down_at is not None:
            raise ConflictError(f"Major incident {major_incident_id} is already stood down.")

        incident = await self._incidents.require_in_org(organization_id, declaration.incident_id)
        if incident_status_of(incident.status) not in _CLOSEABLE_STATUSES:
            raise ValidationError(
                f"{incident.reference} is {incident.status!s}; it must be resolved or closed "
                "before major-incident closure can be approved."
            )

        moment = now or datetime.now(UTC)
        declaration.closure_approved_by = approved_by
        declaration.closure_approved_at = moment
        declaration.stood_down_at = moment
        declaration.stood_down_by = approved_by
        return await self._major_incidents.update(declaration)

    async def record_status_update(
        self,
        organization_id: UUID,
        major_incident_id: UUID,
        *,
        summary: str,
        now: datetime | None = None,
    ) -> MajorIncidentEvent:
        """Record that a stakeholder status update went out.

        What the maintenance sweep's overdue-update check reads --
        without this, "have we told stakeholders anything in the last
        thirty minutes" has no answer.
        """
        declaration = await self._major_incidents.require_in_org(organization_id, major_incident_id)
        declaration.last_status_update_at = now or datetime.now(UTC)
        declaration.executive_summary = summary
        return await self._major_incidents.update(declaration)

    async def get_declaration(
        self, organization_id: UUID, incident_id: UUID
    ) -> MajorIncidentEvent | None:
        """The declaration for one incident, if it has been declared major."""
        return await self._major_incidents.get_for_incident(organization_id, incident_id)

    async def get_war_room_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> WarRoom | None:
        """The open war room for one incident, if it has one.

        What a caller who has just declared an incident major needs
        next: ``declare`` opens the war room but its own response is the
        declaration alone, and nothing else on this incident's own
        record carries the war room's id.
        """
        return await self._war_rooms.get_open_for_incident(organization_id, incident_id)

    async def list_active(self, organization_id: UUID) -> list[MajorIncidentEvent]:
        """Every major incident not yet stood down."""
        return await self._major_incidents.list_active(organization_id)

    async def get_war_room(self, organization_id: UUID, war_room_id: UUID) -> WarRoom:
        """One war room.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._war_rooms.require_in_org(organization_id, war_room_id)

    async def participants(
        self, organization_id: UUID, war_room_id: UUID
    ) -> list[WarRoomParticipant]:
        """Everyone who has ever been in a war room, including those who left."""
        return await self._participants.list_all(organization_id, war_room_id)


__all__ = ["MajorIncidentService"]
