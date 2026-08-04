"""MajorIncidentService: declaration, war rooms, participants, closure."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import IncidentStatus, WarRoomRole, WarRoomStatus
from app.services.incident import IncidentService
from app.services.major_incident import MajorIncidentService

pytestmark = pytest.mark.asyncio


class TestDeclare:
    async def test_declare_creates_a_declaration_and_a_war_room(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        declaration, war_room = await major_incident_service.declare(
            organization_id,
            incident.id,
            reason="Estate-wide outage",
            incident_commander_id="alice",
        )
        assert declaration.incident_commander_id == "alice"
        assert war_room.status == WarRoomStatus.OPEN

    async def test_declare_marks_the_incident_major(
        self,
        major_incident_service: MajorIncidentService,
        organization_id,
        make_incident,
        incidents_repo,
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.is_major is True
        assert refreshed.major_incident_id == declaration.id

    async def test_declaring_twice_raises(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await major_incident_service.declare(organization_id, incident.id, reason="Outage")
        with pytest.raises(ConflictError):
            await major_incident_service.declare(organization_id, incident.id, reason="Again")

    async def test_declare_with_a_commander_seats_them_in_the_war_room(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage", incident_commander_id="alice"
        )
        participants = await major_incident_service.participants(organization_id, war_room.id)
        assert any(
            one.participant_id == "alice" and one.role == WarRoomRole.INCIDENT_COMMANDER
            for one in participants
        )

    async def test_list_active_finds_the_new_declaration(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        active = await major_incident_service.list_active(organization_id)
        assert declaration.id in {one.id for one in active}


class TestWarRoomRoles:
    async def test_assign_role_seats_a_participant(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        participant = await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="bob", role=WarRoomRole.TECHNICAL_LEAD
        )
        assert participant.role == WarRoomRole.TECHNICAL_LEAD

    async def test_a_singleton_role_cannot_be_double_assigned(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="alice", role=WarRoomRole.TECHNICAL_LEAD
        )
        with pytest.raises(ConflictError):
            await major_incident_service.assign_role(
                organization_id, war_room.id, participant_id="bob", role=WarRoomRole.TECHNICAL_LEAD
            )

    async def test_reassigning_the_same_role_to_the_same_person_is_allowed(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="alice", role=WarRoomRole.TECHNICAL_LEAD
        )
        second = await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="alice", role=WarRoomRole.TECHNICAL_LEAD
        )
        assert second.participant_id == "alice"

    async def test_a_non_singleton_role_may_have_many_participants(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="alice", role=WarRoomRole.PARTICIPANT
        )
        await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="bob", role=WarRoomRole.PARTICIPANT
        )
        participants = await major_incident_service.participants(organization_id, war_room.id)
        assert len({one.participant_id for one in participants}) >= 2

    async def test_leave_marks_a_participant_as_having_left(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await major_incident_service.assign_role(
            organization_id, war_room.id, participant_id="alice", role=WarRoomRole.PARTICIPANT
        )
        await major_incident_service.leave(organization_id, war_room.id, participant_id="alice")
        participants = await major_incident_service.participants(organization_id, war_room.id)
        alice = next(one for one in participants if one.participant_id == "alice")
        assert alice.left_at is not None


class TestSharedNotesAndStandDown:
    async def test_add_shared_note_appends(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        first = await major_incident_service.add_shared_note(
            organization_id, war_room.id, note="Investigating."
        )
        second = await major_incident_service.add_shared_note(
            organization_id, war_room.id, note="Found root cause."
        )
        assert "Investigating." in second.shared_notes
        assert "Found root cause." in second.shared_notes
        assert first.id == second.id

    async def test_stand_down_closes_the_war_room(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        closed = await major_incident_service.stand_down(
            organization_id, war_room.id, stood_down_by="alice"
        )
        assert closed.status == WarRoomStatus.CLOSED
        assert closed.closed_at is not None

    async def test_standing_down_an_already_closed_room_raises(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await major_incident_service.stand_down(organization_id, war_room.id)
        with pytest.raises(ConflictError):
            await major_incident_service.stand_down(organization_id, war_room.id)


class TestApproveClosure:
    async def test_approve_closure_requires_the_incident_to_be_resolved(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        with pytest.raises(ValidationError):
            await major_incident_service.approve_closure(
                organization_id, declaration.id, approved_by="director-1"
            )

    async def test_approve_closure_succeeds_once_resolved(
        self,
        major_incident_service: MajorIncidentService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.RESOLVED
        )
        approved = await major_incident_service.approve_closure(
            organization_id, declaration.id, approved_by="director-1"
        )
        assert approved.closure_approved_by == "director-1"
        assert approved.stood_down_at is not None

    async def test_approving_closure_twice_raises(
        self,
        major_incident_service: MajorIncidentService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.RESOLVED
        )
        await major_incident_service.approve_closure(
            organization_id, declaration.id, approved_by="director-1"
        )
        with pytest.raises(ConflictError):
            await major_incident_service.approve_closure(
                organization_id, declaration.id, approved_by="director-1"
            )

    async def test_record_status_update_stamps_the_time_and_summary(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        updated = await major_incident_service.record_status_update(
            organization_id, declaration.id, summary="Still investigating."
        )
        assert updated.executive_summary == "Still investigating."
        assert updated.last_status_update_at is not None

    async def test_get_declaration_returns_none_when_never_declared(
        self, major_incident_service: MajorIncidentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        found = await major_incident_service.get_declaration(organization_id, incident.id)
        assert found is None
