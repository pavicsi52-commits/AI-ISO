"""CalendarService: maintenance windows, blackout periods, availability.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import CalendarEntryKind, RecurrenceKind
from app.services.calendar import CalendarService

pytestmark = pytest.mark.asyncio


class TestCreateEntry:
    async def test_creates_a_maintenance_window(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        starts = datetime(2027, 3, 1, 10, 0, tzinfo=UTC)
        ends = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
        created = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Patch window",
            starts_at=starts,
            ends_at=ends,
        )
        assert created.kind == CalendarEntryKind.MAINTENANCE_WINDOW
        assert created.recurrence == RecurrenceKind.NONE
        assert created.is_org_wide is True
        assert created.capacity_limit is None

    async def test_creates_a_blackout_period(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        created = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.BLACKOUT_PERIOD,
            title="Holiday freeze",
            starts_at=datetime(2027, 12, 24, tzinfo=UTC),
            ends_at=datetime(2027, 12, 26, tzinfo=UTC),
        )
        assert created.kind == CalendarEntryKind.BLACKOUT_PERIOD

    async def test_creates_a_recurring_entry_with_capacity(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        created = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Weekly window",
            starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
            ends_at=datetime(2027, 3, 1, 12, 0, tzinfo=UTC),
            recurrence=RecurrenceKind.WEEKLY,
            capacity_limit=3,
        )
        assert created.recurrence == RecurrenceKind.WEEKLY
        assert created.capacity_limit == 3


class TestGet:
    async def test_returns_the_stored_entry(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        created = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Window",
            starts_at=datetime(2027, 1, 1, tzinfo=UTC),
            ends_at=datetime(2027, 1, 1, 1, 0, tzinfo=UTC),
        )
        fetched = await calendar_service.get(organization_id, created.id)
        assert fetched.id == created.id

    async def test_raises_not_found_for_a_missing_entry(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await calendar_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        created = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Window",
            starts_at=datetime(2027, 1, 1, tzinfo=UTC),
            ends_at=datetime(2027, 1, 1, 1, 0, tzinfo=UTC),
        )
        with pytest.raises(NotFoundError):
            await calendar_service.get(uuid4(), created.id)


class TestListOccurrencesInRange:
    async def test_a_non_recurring_entry_touching_the_range_is_returned_once(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        starts = datetime(2027, 5, 10, 9, 0, tzinfo=UTC)
        ends = datetime(2027, 5, 10, 11, 0, tzinfo=UTC)
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="One-off window",
            starts_at=starts,
            ends_at=ends,
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 5, 1, tzinfo=UTC),
            end=datetime(2027, 6, 1, tzinfo=UTC),
        )
        assert len(results) == 1
        _entry, occurrences = results[0]
        assert occurrences == [(starts, ends)]

    async def test_a_non_recurring_entry_outside_the_range_is_excluded(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Far window",
            starts_at=datetime(2027, 8, 1, tzinfo=UTC),
            ends_at=datetime(2027, 8, 1, 1, 0, tzinfo=UTC),
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 5, 1, tzinfo=UTC),
            end=datetime(2027, 6, 1, tzinfo=UTC),
        )
        assert results == []

    async def test_a_daily_recurrence_expands_to_every_day_touching_the_range(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Daily backup window",
            starts_at=datetime(2027, 6, 1, 2, 0, tzinfo=UTC),
            ends_at=datetime(2027, 6, 1, 3, 0, tzinfo=UTC),
            recurrence=RecurrenceKind.DAILY,
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 6, 1, tzinfo=UTC),
            end=datetime(2027, 6, 6, tzinfo=UTC),
        )
        assert len(results) == 1
        _entry, occurrences = results[0]
        assert len(occurrences) == 5

    async def test_a_recurrence_until_cuts_off_expansion_early(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Short-lived daily window",
            starts_at=datetime(2027, 6, 1, 2, 0, tzinfo=UTC),
            ends_at=datetime(2027, 6, 1, 3, 0, tzinfo=UTC),
            recurrence=RecurrenceKind.DAILY,
            recurrence_until=datetime(2027, 6, 3, tzinfo=UTC),
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 6, 1, tzinfo=UTC),
            end=datetime(2027, 6, 30, tzinfo=UTC),
        )
        assert len(results) == 1
        _entry, occurrences = results[0]
        assert len(occurrences) == 2

    async def test_a_monthly_recurrence_anchored_on_the_31st_snaps_back_rather_than_drifting(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Monthly window on the 31st",
            starts_at=datetime(2027, 1, 31, 10, 0, tzinfo=UTC),
            ends_at=datetime(2027, 1, 31, 11, 0, tzinfo=UTC),
            recurrence=RecurrenceKind.MONTHLY,
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 1, 1, tzinfo=UTC),
            end=datetime(2027, 4, 2, tzinfo=UTC),
        )
        assert len(results) == 1
        _entry, occurrences = results[0]
        days = [occ_start.day for occ_start, _ in occurrences]
        assert days == [31, 28, 31]

    async def test_kind_filter_excludes_other_kinds(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Window",
            starts_at=datetime(2027, 9, 1, tzinfo=UTC),
            ends_at=datetime(2027, 9, 1, 1, 0, tzinfo=UTC),
        )
        await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.BLACKOUT_PERIOD,
            title="Freeze",
            starts_at=datetime(2027, 9, 1, tzinfo=UTC),
            ends_at=datetime(2027, 9, 1, 1, 0, tzinfo=UTC),
        )
        results = await calendar_service.list_occurrences_in_range(
            organization_id,
            start=datetime(2027, 9, 1, tzinfo=UTC),
            end=datetime(2027, 9, 2, tzinfo=UTC),
            kind=CalendarEntryKind.BLACKOUT_PERIOD,
        )
        assert len(results) == 1
        assert results[0][0].kind == CalendarEntryKind.BLACKOUT_PERIOD


class TestCheckAvailability:
    async def test_raises_not_found_for_a_missing_entry(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await calendar_service.check_availability(organization_id, uuid4())

    async def test_uncapped_window_is_always_available(
        self, calendar_service: CalendarService, organization_id
    ) -> None:
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Uncapped window",
            starts_at=datetime(2027, 2, 1, tzinfo=UTC),
            ends_at=datetime(2027, 2, 1, 1, 0, tzinfo=UTC),
        )
        check = await calendar_service.check_availability(organization_id, entry.id)
        assert check.is_available is True
        assert check.reason is None

    async def test_a_capped_window_under_capacity_is_available(
        self,
        calendar_service: CalendarService,
        change_service,
        make_approved_change,
        organization_id,
    ) -> None:
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Capped window",
            starts_at=datetime(2027, 2, 1, tzinfo=UTC),
            ends_at=datetime(2027, 2, 1, 1, 0, tzinfo=UTC),
            capacity_limit=2,
        )
        change = await make_approved_change()
        await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=entry.id,
            scheduled_start_at=entry.starts_at,
            scheduled_end_at=entry.ends_at,
        )
        check = await calendar_service.check_availability(organization_id, entry.id)
        assert check.is_available is True

    async def test_a_window_at_capacity_is_unavailable_with_a_reason(
        self,
        calendar_service: CalendarService,
        change_service,
        make_approved_change,
        organization_id,
    ) -> None:
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Full window",
            starts_at=datetime(2027, 2, 1, tzinfo=UTC),
            ends_at=datetime(2027, 2, 1, 1, 0, tzinfo=UTC),
            capacity_limit=1,
        )
        change = await make_approved_change()
        await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=entry.id,
            scheduled_start_at=entry.starts_at,
            scheduled_end_at=entry.ends_at,
        )
        check = await calendar_service.check_availability(organization_id, entry.id)
        assert check.is_available is False
        assert "1/1" in check.reason

    async def test_exclude_change_id_leaves_room_for_the_change_being_rescheduled(
        self,
        calendar_service: CalendarService,
        change_service,
        make_approved_change,
        organization_id,
    ) -> None:
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Full window",
            starts_at=datetime(2027, 2, 1, tzinfo=UTC),
            ends_at=datetime(2027, 2, 1, 1, 0, tzinfo=UTC),
            capacity_limit=1,
        )
        change = await make_approved_change()
        scheduled = await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=entry.id,
            scheduled_start_at=entry.starts_at,
            scheduled_end_at=entry.ends_at,
        )
        check = await calendar_service.check_availability(
            organization_id, entry.id, exclude_change_id=scheduled.id
        )
        assert check.is_available is True
