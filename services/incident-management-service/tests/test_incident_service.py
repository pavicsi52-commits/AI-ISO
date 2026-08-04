"""IncidentService: creation, correlation, lifecycle, assignment, merging.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import (
    AssignmentMethod,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
)
from app.services.incident import IncidentService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_creates_a_new_incident_with_a_reference(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, is_new = await incident_service.create(organization_id, title="Disk full")
        assert is_new is True
        assert created.reference.startswith("INC-")
        assert created.status == IncidentStatus.NEW

    async def test_reference_sequence_increments(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        first, _ = await incident_service.create(organization_id, title="A")
        second, _ = await incident_service.create(organization_id, title="B")
        first_seq = int(first.reference.rsplit("-", 1)[1])
        second_seq = int(second.reference.rsplit("-", 1)[1])
        assert second_seq == first_seq + 1

    async def test_creates_a_timeline_entry_on_open(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="Disk full")
        entries = await incident_service.timeline(organization_id, created.id)
        assert len(entries) == 1
        assert "opened" in entries[0].summary.lower()

    async def test_publishes_incident_created_event(
        self, incident_service: IncidentService, organization_id, publisher
    ) -> None:
        await incident_service.create(organization_id, title="Disk full")
        assert "IncidentCreated" in publisher.names

    async def test_correlates_onto_an_open_incident_sharing_a_fingerprint(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        first, is_new_1 = await incident_service.create(
            organization_id,
            title="High CPU",
            source=IncidentSource.MONITORING,
            category=IncidentCategory.INFRASTRUCTURE,
            correlation_key="host-1-cpu",
        )
        second, is_new_2 = await incident_service.create(
            organization_id,
            title="High CPU (again)",
            source=IncidentSource.MONITORING,
            category=IncidentCategory.INFRASTRUCTURE,
            correlation_key="host-1-cpu",
        )
        assert is_new_1 is True
        assert is_new_2 is False
        assert second.id == first.id

    async def test_no_correlation_key_never_correlates(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        first, _ = await incident_service.create(organization_id, title="A")
        second, is_new = await incident_service.create(organization_id, title="B")
        assert is_new is True
        assert second.id != first.id

    async def test_a_closed_incident_does_not_absorb_a_new_firing(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        first, _ = await incident_service.create(
            organization_id, title="A", correlation_key="k", source=IncidentSource.MONITORING
        )
        await incident_service.transition(organization_id, first.id, target=IncidentStatus.ASSIGNED)
        await incident_service.transition(
            organization_id, first.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, first.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(organization_id, first.id, target=IncidentStatus.RESOLVED)
        await incident_service.transition(organization_id, first.id, target=IncidentStatus.CLOSED)
        second, is_new = await incident_service.create(
            organization_id, title="A again", correlation_key="k", source=IncidentSource.MONITORING
        )
        assert is_new is True
        assert second.id != first.id


class TestGetAndList:
    async def test_get_raises_not_found_for_a_missing_incident(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await incident_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        with pytest.raises(NotFoundError):
            await incident_service.get(uuid4(), created.id)

    async def test_list_filters_by_status(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        await incident_service.create(organization_id, title="A")
        found = await incident_service.list_incidents(organization_id, status=IncidentStatus.NEW)
        assert len(found) >= 1
        assert all(one.status == str(IncidentStatus.NEW) for one in found)

    async def test_list_open_only_excludes_resolved(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.RESOLVED
        )
        found = await incident_service.list_incidents(organization_id, open_only=True)
        assert created.id not in {one.id for one in found}


class TestTransition:
    async def test_new_can_move_to_assigned(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        updated = await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        assert updated.status == IncidentStatus.ASSIGNED

    async def test_illegal_transition_raises(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        with pytest.raises(ValidationError):
            await incident_service.transition(
                organization_id, created.id, target=IncidentStatus.RESOLVED
            )

    async def test_resolving_sets_resolved_at_and_mttr(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        updated = await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.RESOLVED
        )
        assert updated.resolved_at is not None
        assert updated.mttr_seconds is not None

    async def test_reopen_increments_reopen_count_and_clears_resolution(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.RESOLVED
        )
        reopened = await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        assert reopened.reopen_count == 1
        assert reopened.resolved_at is None

    async def test_reopen_publishes_reopened_event(
        self, incident_service: IncidentService, organization_id, publisher
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.RESOLVED
        )
        publisher.events.clear()
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        assert "IncidentReopened" in publisher.names

    async def test_closing_publishes_closed_event(
        self, incident_service: IncidentService, organization_id, publisher
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, created.id, target=IncidentStatus.RESOLVED
        )
        publisher.events.clear()
        await incident_service.transition(organization_id, created.id, target=IncidentStatus.CLOSED)
        assert "IncidentClosed" in publisher.names


class TestAssign:
    async def test_assigning_a_new_incident_moves_it_to_assigned(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        updated = await incident_service.assign(organization_id, created.id, assignee_id="alice")
        assert updated.assignee_id == "alice"
        assert updated.status == IncidentStatus.ASSIGNED
        assert updated.responded_at is not None

    async def test_reassigning_closes_the_prior_assignment(
        self, incident_service: IncidentService, organization_id, assignment_repo
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.assign(organization_id, created.id, assignee_id="alice")
        await incident_service.assign(organization_id, created.id, assignee_id="bob")
        history = await assignment_repo.list_for_incident(organization_id, created.id)
        assert len(history) == 2
        assert history[0].unassigned_at is not None
        assert history[1].assignee_id == "bob"

    async def test_assign_publishes_assigned_event(
        self, incident_service: IncidentService, organization_id, publisher
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.assign(organization_id, created.id, assignee_id="alice")
        assert "IncidentAssigned" in publisher.names

    async def test_assign_records_the_method(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        updated = await incident_service.assign(
            organization_id, created.id, assignee_id="alice", method=AssignmentMethod.LOAD_BALANCED
        )
        assert updated.assignment_method == str(AssignmentMethod.LOAD_BALANCED)


class TestMerge:
    async def test_merges_source_into_target(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        source, _ = await incident_service.create(organization_id, title="Duplicate")
        target, _ = await incident_service.create(organization_id, title="Original")
        updated_source = await incident_service.merge(
            organization_id,
            source_incident_id=source.id,
            target_incident_id=target.id,
            reason="Same root cause",
        )
        assert updated_source.status == IncidentStatus.MERGED
        assert updated_source.merged_into_id == target.id

    async def test_cannot_merge_an_incident_into_itself(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        with pytest.raises(ValidationError):
            await incident_service.merge(
                organization_id,
                source_incident_id=created.id,
                target_incident_id=created.id,
                reason="whoops",
            )

    async def test_cannot_merge_into_an_already_merged_target(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        a, _ = await incident_service.create(organization_id, title="A")
        b, _ = await incident_service.create(organization_id, title="B")
        c, _ = await incident_service.create(organization_id, title="C")
        await incident_service.merge(
            organization_id, source_incident_id=a.id, target_incident_id=b.id, reason="dup"
        )
        with pytest.raises(ValidationError):
            await incident_service.merge(
                organization_id, source_incident_id=c.id, target_incident_id=a.id, reason="dup"
            )

    async def test_a_closed_incident_cannot_be_merged(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        source, _ = await incident_service.create(organization_id, title="A")
        target, _ = await incident_service.create(organization_id, title="B")
        await incident_service.transition(
            organization_id, source.id, target=IncidentStatus.CANCELLED
        )
        with pytest.raises(ConflictError):
            await incident_service.merge(
                organization_id,
                source_incident_id=source.id,
                target_incident_id=target.id,
                reason="dup",
            )


class TestWorklogAndNotes:
    async def test_add_worklog_records_effort(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        entry = await incident_service.add_worklog(
            organization_id, created.id, note="Investigated logs", minutes_spent=15
        )
        assert entry.note == "Investigated logs"
        logs = await incident_service.worklogs(organization_id, created.id)
        assert len(logs) == 1

    async def test_add_worklog_on_a_missing_incident_raises(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await incident_service.add_worklog(organization_id, uuid4(), note="x")

    async def test_add_note_appends_to_timeline(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.add_note(
            organization_id, created.id, summary="Checked in with vendor."
        )
        entries = await incident_service.timeline(organization_id, created.id)
        assert any("vendor" in one.summary for one in entries)

    async def test_timeline_is_ordered_oldest_first(
        self, incident_service: IncidentService, organization_id
    ) -> None:
        created, _ = await incident_service.create(organization_id, title="A")
        await incident_service.add_note(organization_id, created.id, summary="Second note")
        entries = await incident_service.timeline(organization_id, created.id)
        assert entries[0].occurred_at <= entries[-1].occurred_at
