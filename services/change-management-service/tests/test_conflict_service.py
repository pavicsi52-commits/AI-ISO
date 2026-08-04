"""ConflictService: detecting, acknowledging, and resolving scheduling conflicts.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import CalendarEntryKind, ConflictKind, ConflictStatus
from app.services.conflict import ConflictService

pytestmark = pytest.mark.asyncio


class TestDetectForChange:
    async def test_raises_not_found_for_a_missing_change(
        self, conflict_service: ConflictService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await conflict_service.detect_for_change(organization_id, uuid4())

    async def test_an_unscheduled_change_has_nothing_to_compare(
        self, conflict_service: ConflictService, make_change, organization_id
    ) -> None:
        change = await make_change()
        found = await conflict_service.detect_for_change(organization_id, change.id)
        assert found == []

    async def test_two_changes_scheduled_in_the_same_window_conflict_on_schedule(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        await make_scheduled_change()
        found = await conflict_service.detect_for_change(organization_id, first.id)
        assert any(one.kind == ConflictKind.SCHEDULE for one in found)

    async def test_shared_assets_add_an_asset_conflict(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change(affected_assets=["asset-1"])
        await make_scheduled_change(affected_assets=["asset-1"])
        found = await conflict_service.detect_for_change(organization_id, first.id)
        kinds = {one.kind for one in found}
        assert ConflictKind.SCHEDULE in kinds
        assert ConflictKind.ASSET in kinds

    async def test_shared_services_add_a_service_conflict(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change(affected_services=["svc-1"])
        await make_scheduled_change(affected_services=["svc-1"])
        found = await conflict_service.detect_for_change(organization_id, first.id)
        kinds = {one.kind for one in found}
        assert ConflictKind.SERVICE in kinds

    async def test_shared_applications_add_an_application_conflict(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change(affected_applications=["app-1"])
        await make_scheduled_change(affected_applications=["app-1"])
        found = await conflict_service.detect_for_change(organization_id, first.id)
        kinds = {one.kind for one in found}
        assert ConflictKind.APPLICATION in kinds

    async def test_windows_separated_within_slack_still_conflict(
        self,
        conflict_service: ConflictService,
        change_service,
        calendar_service,
        make_approved_change,
        organization_id,
    ) -> None:
        base = datetime(2027, 4, 1, 10, 0, tzinfo=UTC)
        first_change = await make_approved_change()
        first_entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="First window",
            starts_at=base,
            ends_at=base + timedelta(hours=1),
        )
        first = await change_service.schedule(
            organization_id,
            first_change.id,
            calendar_entry_id=first_entry.id,
            scheduled_start_at=base,
            scheduled_end_at=base + timedelta(hours=1),
        )
        second_change = await make_approved_change()
        second_entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Second window",
            starts_at=base + timedelta(hours=4),
            ends_at=base + timedelta(hours=5),
        )
        await change_service.schedule(
            organization_id,
            second_change.id,
            calendar_entry_id=second_entry.id,
            scheduled_start_at=base + timedelta(hours=4),
            scheduled_end_at=base + timedelta(hours=5),
        )
        found = await conflict_service.detect_for_change(organization_id, first.id)
        assert any(one.kind == ConflictKind.SCHEDULE for one in found)

    async def test_windows_separated_beyond_slack_do_not_conflict(
        self,
        conflict_service: ConflictService,
        change_service,
        calendar_service,
        make_approved_change,
        organization_id,
    ) -> None:
        base = datetime(2027, 4, 1, 10, 0, tzinfo=UTC)
        first_change = await make_approved_change()
        first_entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="First window",
            starts_at=base,
            ends_at=base + timedelta(hours=1),
        )
        first = await change_service.schedule(
            organization_id,
            first_change.id,
            calendar_entry_id=first_entry.id,
            scheduled_start_at=base,
            scheduled_end_at=base + timedelta(hours=1),
        )
        second_change = await make_approved_change()
        second_entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Second window",
            starts_at=base + timedelta(hours=20),
            ends_at=base + timedelta(hours=21),
        )
        await change_service.schedule(
            organization_id,
            second_change.id,
            calendar_entry_id=second_entry.id,
            scheduled_start_at=base + timedelta(hours=20),
            scheduled_end_at=base + timedelta(hours=21),
        )
        found = await conflict_service.detect_for_change(organization_id, first.id)
        assert found == []

    async def test_detection_is_idempotent(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        await make_scheduled_change()
        first_pass = await conflict_service.detect_for_change(organization_id, first.id)
        assert first_pass != []
        second_pass = await conflict_service.detect_for_change(organization_id, first.id)
        assert second_pass == []
        still_there = await conflict_service.list_for_change(organization_id, first.id)
        assert len(still_there) == len(first_pass)


class TestAcknowledgeAndResolve:
    async def test_acknowledge_raises_not_found_for_a_missing_conflict(
        self, conflict_service: ConflictService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await conflict_service.acknowledge(organization_id, uuid4())

    async def test_acknowledge_moves_status_to_acknowledged(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        await make_scheduled_change()
        [conflict, *_] = await conflict_service.detect_for_change(organization_id, first.id)
        updated = await conflict_service.acknowledge(organization_id, conflict.id)
        assert updated.status == ConflictStatus.ACKNOWLEDGED

    async def test_resolve_raises_not_found_for_a_missing_conflict(
        self, conflict_service: ConflictService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await conflict_service.resolve(organization_id, uuid4(), resolved_by="ops-1")

    async def test_resolve_records_who_and_why(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        await make_scheduled_change()
        [conflict, *_] = await conflict_service.detect_for_change(organization_id, first.id)
        updated = await conflict_service.resolve(
            organization_id, conflict.id, resolved_by="ops-1", note="Rescheduled the second one."
        )
        assert updated.status == ConflictStatus.RESOLVED
        assert updated.resolved_by == "ops-1"
        assert updated.resolved_at is not None
        assert updated.resolution_note == "Rescheduled the second one."


class TestListForChangeAndListActive:
    async def test_list_for_change_finds_conflicts_on_either_side(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        second = await make_scheduled_change()
        await conflict_service.detect_for_change(organization_id, first.id)
        found_as_target = await conflict_service.list_for_change(organization_id, first.id)
        found_as_other = await conflict_service.list_for_change(organization_id, second.id)
        assert len(found_as_target) > 0
        assert len(found_as_other) > 0

    async def test_list_active_excludes_resolved_conflicts(
        self, conflict_service: ConflictService, make_scheduled_change, organization_id
    ) -> None:
        first = await make_scheduled_change()
        await make_scheduled_change()
        detected = await conflict_service.detect_for_change(organization_id, first.id)
        active_before = await conflict_service.list_active(organization_id)
        assert any(one.id == detected[0].id for one in active_before)
        await conflict_service.resolve(organization_id, detected[0].id, resolved_by="ops-1")
        active_after = await conflict_service.list_active(organization_id)
        assert all(one.id != detected[0].id for one in active_after)
