"""ChangeService: creation, editing, lifecycle, scheduling, relationships.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from tests.conftest import soon

from app.models.enums import (
    CalendarEntryKind,
    ChangeCategory,
    ChangePriority,
    ChangeStatus,
    RelationshipKind,
)
from app.services.calendar import CalendarService
from app.services.change import ChangeService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_creates_a_new_change_in_draft_with_a_chg_reference(
        self, change_service: ChangeService, organization_id
    ) -> None:
        created = await change_service.create(
            organization_id, title="Patch the payments gateway", requester_id="requester-1"
        )
        assert created.reference.startswith("CHG-")
        assert created.status == ChangeStatus.DRAFT

    async def test_reference_sequence_increments_across_calls(
        self, change_service: ChangeService, organization_id
    ) -> None:
        first = await change_service.create(organization_id, title="A", requester_id="requester-1")
        second = await change_service.create(organization_id, title="B", requester_id="requester-1")
        first_seq = int(first.reference.rsplit("-", 1)[1])
        second_seq = int(second.reference.rsplit("-", 1)[1])
        assert second_seq == first_seq + 1

    async def test_publishes_change_created_event(
        self, change_service: ChangeService, organization_id, publisher
    ) -> None:
        await change_service.create(organization_id, title="A", requester_id="requester-1")
        assert "ChangeCreated" in publisher.names


class TestGet:
    async def test_raises_not_found_for_a_missing_change(
        self, change_service: ChangeService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await change_service.get(organization_id, uuid4())

    async def test_is_scoped_to_its_organization(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(NotFoundError):
            await change_service.get(uuid4(), created.id)


class TestListChanges:
    async def test_filters_by_status(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        found = await change_service.list_changes(organization_id, status=ChangeStatus.DRAFT)
        assert created.id in {one.id for one in found}
        assert all(one.status == ChangeStatus.DRAFT for one in found)

    async def test_filters_by_priority(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        high = await make_change(priority=ChangePriority.HIGH)
        await make_change(priority=ChangePriority.LOW)
        found = await change_service.list_changes(organization_id, priority=ChangePriority.HIGH)
        ids = {one.id for one in found}
        assert high.id in ids
        assert all(one.priority == ChangePriority.HIGH for one in found)

    async def test_filters_by_category(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        security = await make_change(category=ChangeCategory.SECURITY)
        await make_change(category=ChangeCategory.DATABASE)
        found = await change_service.list_changes(organization_id, category=ChangeCategory.SECURITY)
        ids = {one.id for one in found}
        assert security.id in ids
        assert all(one.category == ChangeCategory.SECURITY for one in found)

    async def test_filters_by_technical_owner_id(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        owned = await make_change(technical_owner_id="alice")
        await make_change(technical_owner_id="bob")
        found = await change_service.list_changes(organization_id, technical_owner_id="alice")
        ids = {one.id for one in found}
        assert owned.id in ids
        assert all(one.technical_owner_id == "alice" for one in found)

    async def test_open_only_excludes_a_cancelled_change(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        still_open = await make_change()
        cancelled = await make_change()
        await change_service.transition(
            organization_id, cancelled.id, target=ChangeStatus.CANCELLED
        )
        found = await change_service.list_changes(organization_id, open_only=True)
        ids = {one.id for one in found}
        assert still_open.id in ids
        assert cancelled.id not in ids


class TestUpdate:
    async def test_updates_a_draft_changes_own_fields(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        updated = await change_service.update(organization_id, created.id, title="A better title")
        assert updated.title == "A better title"

    async def test_raises_conflict_once_the_change_has_been_submitted(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        with pytest.raises(ConflictError):
            await change_service.update(organization_id, created.id, title="Too late")


class TestSubmit:
    async def test_sets_submitted_at_and_moves_to_submitted(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        updated = await change_service.submit(organization_id, created.id)
        assert updated.status == ChangeStatus.SUBMITTED
        assert updated.submitted_at is not None

    async def test_publishes_change_submitted_event(
        self, change_service: ChangeService, organization_id, make_change, publisher
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        assert "ChangeSubmitted" in publisher.names

    async def test_submitting_an_already_submitted_change_raises_validation_error(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        with pytest.raises(ValidationError):
            await change_service.submit(organization_id, created.id)


class TestTransition:
    async def test_illegal_transition_raises_validation_error(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ValidationError):
            await change_service.transition(
                organization_id, created.id, target=ChangeStatus.COMPLETED
            )

    async def test_completed_and_closed_each_set_their_own_timestamp(
        self, change_service: ChangeService, organization_id, make_approved_change
    ) -> None:
        change = await make_approved_change()
        await change_service.transition(organization_id, change.id, target=ChangeStatus.SCHEDULED)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.READY)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.IN_PROGRESS)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.VALIDATION)
        completed = await change_service.transition(
            organization_id, change.id, target=ChangeStatus.COMPLETED
        )
        assert completed.completed_at is not None
        assert completed.closed_at is None
        closed = await change_service.transition(
            organization_id, change.id, target=ChangeStatus.CLOSED
        )
        assert closed.closed_at is not None


class TestSchedule:
    async def test_raises_not_found_for_a_calendar_entry_that_does_not_exist(
        self, change_service: ChangeService, organization_id, make_approved_change
    ) -> None:
        change = await make_approved_change()
        with pytest.raises(NotFoundError):
            await change_service.schedule(
                organization_id,
                change.id,
                calendar_entry_id=uuid4(),
                scheduled_start_at=soon(1),
                scheduled_end_at=soon(2),
            )

    async def test_raises_validation_error_when_the_change_is_not_eligible(
        self,
        change_service: ChangeService,
        calendar_service: CalendarService,
        organization_id,
        make_change,
    ) -> None:
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Weekend window",
            starts_at=soon(1),
            ends_at=soon(2),
        )
        created = await make_change()
        with pytest.raises(ValidationError):
            await change_service.schedule(
                organization_id,
                created.id,
                calendar_entry_id=entry.id,
                scheduled_start_at=soon(1),
                scheduled_end_at=soon(2),
            )

    async def test_schedule_moves_to_scheduled_and_publishes_event(
        self,
        change_service: ChangeService,
        calendar_service: CalendarService,
        organization_id,
        make_approved_change,
        publisher,
    ) -> None:
        change = await make_approved_change()
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Weekend window",
            starts_at=soon(1),
            ends_at=soon(2),
        )
        updated = await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=entry.id,
            scheduled_start_at=soon(1),
            scheduled_end_at=soon(2),
        )
        assert updated.status == ChangeStatus.SCHEDULED
        assert updated.calendar_entry_id == entry.id
        assert "ChangeScheduled" in publisher.names


class TestMarkReady:
    async def test_moves_a_scheduled_change_to_ready(
        self, change_service: ChangeService, organization_id, make_approved_change
    ) -> None:
        change = await make_approved_change()
        await change_service.transition(organization_id, change.id, target=ChangeStatus.SCHEDULED)
        updated = await change_service.mark_ready(organization_id, change.id)
        assert updated.status == ChangeStatus.READY

    async def test_raises_validation_error_from_an_ineligible_status(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ValidationError):
            await change_service.mark_ready(organization_id, created.id)


class TestClose:
    async def test_closes_a_completed_change(
        self, change_service: ChangeService, organization_id, make_approved_change
    ) -> None:
        change = await make_approved_change()
        await change_service.transition(organization_id, change.id, target=ChangeStatus.SCHEDULED)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.READY)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.IN_PROGRESS)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.VALIDATION)
        await change_service.transition(organization_id, change.id, target=ChangeStatus.COMPLETED)
        closed = await change_service.close(organization_id, change.id)
        assert closed.status == ChangeStatus.CLOSED
        assert closed.closed_at is not None

    async def test_raises_validation_error_from_an_ineligible_status(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ValidationError):
            await change_service.close(organization_id, created.id)


class TestLinkRelationship:
    async def test_creates_a_relationship_between_two_changes(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        source = await make_change()
        target = await make_change()
        relationship = await change_service.link_relationship(
            organization_id,
            source.id,
            related_change_id=target.id,
            kind=RelationshipKind.DEPENDS_ON,
        )
        assert relationship.change_id == source.id
        assert relationship.related_change_id == target.id
        assert relationship.kind == RelationshipKind.DEPENDS_ON

    async def test_cannot_relate_a_change_to_itself(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ValidationError):
            await change_service.link_relationship(
                organization_id,
                created.id,
                related_change_id=created.id,
                kind=RelationshipKind.RELATED_TO,
            )

    async def test_raises_not_found_when_the_source_change_does_not_exist(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        target = await make_change()
        with pytest.raises(NotFoundError):
            await change_service.link_relationship(
                organization_id,
                uuid4(),
                related_change_id=target.id,
                kind=RelationshipKind.RELATED_TO,
            )

    async def test_raises_not_found_when_the_related_change_does_not_exist(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        source = await make_change()
        with pytest.raises(NotFoundError):
            await change_service.link_relationship(
                organization_id,
                source.id,
                related_change_id=uuid4(),
                kind=RelationshipKind.RELATED_TO,
            )


class TestListRelationships:
    async def test_lists_only_the_relationships_this_change_is_the_source_of(
        self, change_service: ChangeService, organization_id, make_change
    ) -> None:
        source = await make_change()
        first_target = await make_change()
        second_target = await make_change()
        await change_service.link_relationship(
            organization_id,
            source.id,
            related_change_id=first_target.id,
            kind=RelationshipKind.DEPENDS_ON,
        )
        await change_service.link_relationship(
            organization_id,
            source.id,
            related_change_id=second_target.id,
            kind=RelationshipKind.BLOCKS,
        )
        found = await change_service.list_relationships(organization_id, source.id)
        assert len(found) == 2
        assert {one.related_change_id for one in found} == {first_target.id, second_target.id}
