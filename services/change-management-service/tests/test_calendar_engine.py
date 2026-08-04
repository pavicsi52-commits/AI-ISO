"""Maintenance windows and blackout periods: recurrence expansion, availability.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.calendar.engine import check_availability, expand_occurrences, is_within_any
from app.models.enums import RecurrenceKind

_JAN_31 = datetime(2026, 1, 31, 22, 0, tzinfo=UTC)


class TestExpandOccurrences:
    def test_non_recurring_entry_expands_to_one_occurrence(self) -> None:
        occurrences = expand_occurrences(
            starts_at=_JAN_31,
            ends_at=_JAN_31 + timedelta(hours=2),
            recurrence=RecurrenceKind.NONE,
            recurrence_until=None,
            window_start=_JAN_31 - timedelta(days=1),
            window_end=_JAN_31 + timedelta(days=30),
        )
        assert occurrences == [(_JAN_31, _JAN_31 + timedelta(hours=2))]

    def test_entry_outside_the_queried_range_produces_nothing(self) -> None:
        occurrences = expand_occurrences(
            starts_at=_JAN_31,
            ends_at=_JAN_31 + timedelta(hours=2),
            recurrence=RecurrenceKind.NONE,
            recurrence_until=None,
            window_start=_JAN_31 + timedelta(days=10),
            window_end=_JAN_31 + timedelta(days=20),
        )
        assert occurrences == []

    def test_daily_recurrence_produces_one_occurrence_per_day(self) -> None:
        start = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
        occurrences = expand_occurrences(
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence=RecurrenceKind.DAILY,
            recurrence_until=None,
            window_start=start,
            window_end=start + timedelta(days=5),
        )
        assert len(occurrences) == 5

    def test_weekly_recurrence_steps_by_seven_days(self) -> None:
        start = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
        occurrences = expand_occurrences(
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence=RecurrenceKind.WEEKLY,
            recurrence_until=None,
            window_start=start,
            window_end=start + timedelta(weeks=3),
        )
        assert [s.day for s, _e in occurrences] == [1, 8, 15]

    def test_monthly_recurrence_clamps_january_31_into_february(self) -> None:
        occurrences = expand_occurrences(
            starts_at=_JAN_31,
            ends_at=_JAN_31 + timedelta(hours=1),
            recurrence=RecurrenceKind.MONTHLY,
            recurrence_until=None,
            window_start=_JAN_31,
            window_end=_JAN_31 + timedelta(days=95),
        )
        months = [(s.year, s.month, s.day) for s, _e in occurrences]
        assert (2026, 1, 31) in months
        assert (2026, 2, 28) in months
        assert (2026, 3, 31) in months

    def test_recurrence_until_stops_expansion_early(self) -> None:
        start = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
        occurrences = expand_occurrences(
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence=RecurrenceKind.DAILY,
            recurrence_until=start + timedelta(days=2),
            window_start=start,
            window_end=start + timedelta(days=30),
        )
        assert len(occurrences) == 2

    def test_expansion_never_exceeds_the_safety_ceiling(self) -> None:
        start = datetime(2020, 1, 1, tzinfo=UTC)
        occurrences = expand_occurrences(
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence=RecurrenceKind.DAILY,
            recurrence_until=None,
            window_start=start,
            window_end=start + timedelta(days=10_000),
        )
        assert len(occurrences) <= 366


class TestIsWithinAny:
    def test_a_moment_inside_an_occurrence_is_within(self) -> None:
        occurrences = [(_JAN_31, _JAN_31 + timedelta(hours=2))]
        assert is_within_any(_JAN_31 + timedelta(hours=1), occurrences) is True

    def test_a_moment_outside_every_occurrence_is_not_within(self) -> None:
        occurrences = [(_JAN_31, _JAN_31 + timedelta(hours=2))]
        assert is_within_any(_JAN_31 + timedelta(hours=5), occurrences) is False

    def test_the_end_boundary_is_exclusive(self) -> None:
        end = _JAN_31 + timedelta(hours=2)
        occurrences = [(_JAN_31, end)]
        assert is_within_any(end, occurrences) is False


class TestCheckAvailability:
    def test_no_capacity_limit_is_always_available(self) -> None:
        result = check_availability(capacity_limit=None, current_bookings=1_000)
        assert result.is_available is True

    def test_under_capacity_is_available(self) -> None:
        result = check_availability(capacity_limit=5, current_bookings=2)
        assert result.is_available is True

    def test_at_capacity_is_not_available(self) -> None:
        result = check_availability(capacity_limit=5, current_bookings=5)
        assert result.is_available is False
        assert result.reason is not None
