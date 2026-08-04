"""The SLA clock: due dates, pausing, elapsed time, breach, warnings.

Pure -- no fixtures, no database. Business-hours arithmetic is the part
worth being suspicious of, since it is the part most likely to be
subtly wrong in a way that only shows up once a clock crosses a weekend.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.sla.engine import (
    ALWAYS_OPEN,
    BusinessCalendar,
    ClockState,
    add_business_minutes,
    compliance_rate,
    due_at_for,
    elapsed_seconds,
    is_breached,
    resume_paused_seconds,
    should_warn,
    warning_threshold_at,
)

BUSINESS_HOURS = BusinessCalendar(start_hour=9, end_hour=17)


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestBusinessCalendar:
    def test_is_open_respects_hours_and_days(self) -> None:
        monday_ten = at(2026, 8, 3, 10, 0)  # a Monday
        assert BUSINESS_HOURS.is_open(monday_ten) is True
        assert BUSINESS_HOURS.is_open(monday_ten.replace(hour=8)) is False
        assert BUSINESS_HOURS.is_open(monday_ten.replace(hour=17)) is False, "end_hour is exclusive"

    def test_saturday_is_never_open_on_the_default_calendar(self) -> None:
        saturday = at(2026, 8, 8, 12, 0)
        assert BUSINESS_HOURS.is_open(saturday) is False

    def test_next_open_from_inside_hours_is_now(self) -> None:
        monday_ten = at(2026, 8, 3, 10, 0)
        assert BUSINESS_HOURS.next_open(monday_ten) == monday_ten

    def test_next_open_from_after_hours_rolls_to_next_morning(self) -> None:
        monday_evening = at(2026, 8, 3, 20, 0)
        assert BUSINESS_HOURS.next_open(monday_evening) == at(2026, 8, 4, 9, 0)

    def test_next_open_from_friday_evening_rolls_to_monday(self) -> None:
        friday_evening = at(2026, 8, 7, 20, 0)
        assert BUSINESS_HOURS.next_open(friday_evening) == at(2026, 8, 10, 9, 0)

    def test_always_open_calendar_is_open_at_any_hour(self) -> None:
        assert ALWAYS_OPEN.is_open(at(2026, 8, 8, 3, 0)) is True


class TestAddBusinessMinutes:
    def test_within_one_day_is_simple_addition(self) -> None:
        start = at(2026, 8, 3, 10, 0)
        assert add_business_minutes(start, 60, calendar=BUSINESS_HOURS) == at(2026, 8, 3, 11, 0)

    def test_crossing_a_day_boundary_skips_closed_hours(self) -> None:
        # 30 minutes of room today (16:30->17:00), then 30 more tomorrow.
        start = at(2026, 8, 3, 16, 30)
        assert add_business_minutes(start, 60, calendar=BUSINESS_HOURS) == at(2026, 8, 4, 9, 30)

    def test_crossing_a_weekend_skips_to_monday(self) -> None:
        # Friday 16:30, 8 hours of SLA: 30 min left Friday, 450 more
        # from Monday 9:00 -> 16:30.
        start = at(2026, 8, 7, 16, 30)
        due = add_business_minutes(start, 8 * 60, calendar=BUSINESS_HOURS)
        assert due == at(2026, 8, 10, 16, 30)

    def test_starting_outside_business_hours_rolls_forward_first(self) -> None:
        saturday = at(2026, 8, 8, 12, 0)
        due = add_business_minutes(saturday, 60, calendar=BUSINESS_HOURS)
        assert due == at(2026, 8, 10, 10, 0)

    def test_zero_minutes_is_the_next_open_instant(self) -> None:
        saturday = at(2026, 8, 8, 12, 0)
        assert add_business_minutes(saturday, 0, calendar=BUSINESS_HOURS) == at(2026, 8, 10, 9, 0)

    def test_negative_minutes_is_refused(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            add_business_minutes(at(2026, 8, 3, 10, 0), -5, calendar=BUSINESS_HOURS)

    def test_a_24x7_calendar_never_skips_anything(self) -> None:
        start = at(2026, 8, 7, 16, 30)  # Friday
        due = add_business_minutes(start, 4 * 60, calendar=ALWAYS_OPEN)
        assert due == at(2026, 8, 7, 20, 30)

    def test_a_calendar_with_no_open_days_fails_loudly(self) -> None:
        empty = BusinessCalendar(start_hour=9, end_hour=17, business_days=frozenset())
        with pytest.raises(ValueError, match="No open business hour"):
            empty.next_open(at(2026, 8, 3, 10, 0))


class TestDueAtFor:
    def test_24x7_routes_through_always_open(self) -> None:
        start = at(2026, 8, 7, 16, 30)
        due = due_at_for(start, 4 * 60, is_24x7=True, calendar=BUSINESS_HOURS)
        assert due == at(2026, 8, 7, 20, 30), "is_24x7 must bypass the passed-in calendar"

    def test_business_hours_routes_through_the_given_calendar(self) -> None:
        start = at(2026, 8, 3, 16, 30)
        due = due_at_for(start, 60, is_24x7=False, calendar=BUSINESS_HOURS)
        assert due == at(2026, 8, 4, 9, 30)


class TestElapsedAndBreach:
    def test_elapsed_is_zero_before_the_clock_starts(self) -> None:
        state = ClockState(None, None, None, 0.0, None, None)
        assert elapsed_seconds(state, now=at(2026, 8, 3, 10, 0)) == 0.0

    def test_elapsed_counts_running_time(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), None, None, 0.0, None, None)
        assert elapsed_seconds(state, now=at(2026, 8, 3, 10, 30)) == 1_800.0

    def test_elapsed_subtracts_completed_pauses(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), None, None, 600.0, None, None)
        assert elapsed_seconds(state, now=at(2026, 8, 3, 10, 30)) == 1_200.0

    def test_elapsed_subtracts_a_pause_still_in_progress(self) -> None:
        # Started at 10:00, paused at 10:10, now is 10:30 -- 10 min ran,
        # 20 min (still paused) must not count.
        state = ClockState(at(2026, 8, 3, 10, 0), None, at(2026, 8, 3, 10, 10), 0.0, None, None)
        assert elapsed_seconds(state, now=at(2026, 8, 3, 10, 30)) == 600.0

    def test_elapsed_stops_at_met_or_breach_not_at_now(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), None, None, 0.0, at(2026, 8, 3, 10, 20), None)
        # Time after the clock was met must not keep accumulating.
        assert elapsed_seconds(state, now=at(2026, 8, 3, 12, 0)) == 1_200.0

    def test_a_clock_with_no_due_date_never_breaches(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), None, None, 0.0, None, None)
        assert is_breached(state, now=at(2026, 8, 3, 23, 0)) is False

    def test_a_clock_past_its_due_date_is_breached(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), at(2026, 8, 3, 11, 0), None, 0.0, None, None)
        assert is_breached(state, now=at(2026, 8, 3, 11, 1)) is True
        assert is_breached(state, now=at(2026, 8, 3, 10, 59)) is False

    def test_a_paused_clock_never_breaches_while_paused(self) -> None:
        # Otherwise pausing would stop protecting anyone.
        state = ClockState(
            at(2026, 8, 3, 10, 0),
            at(2026, 8, 3, 11, 0),
            at(2026, 8, 3, 10, 30),
            0.0,
            None,
            None,
        )
        assert is_breached(state, now=at(2026, 8, 3, 12, 0)) is False

    def test_a_clock_already_met_does_not_re_evaluate_as_breached(self) -> None:
        # Reopening the question every read would let a correctly-met
        # clock start reporting breached once "now" passes its due date.
        state = ClockState(
            at(2026, 8, 3, 10, 0),
            at(2026, 8, 3, 11, 0),
            None,
            0.0,
            at(2026, 8, 3, 10, 45),
            None,
        )
        assert is_breached(state, now=at(2026, 8, 3, 23, 0)) is False

    def test_a_clock_already_breached_stays_breached(self) -> None:
        state = ClockState(
            at(2026, 8, 3, 10, 0),
            at(2026, 8, 3, 11, 0),
            None,
            0.0,
            None,
            at(2026, 8, 3, 11, 5),
        )
        assert is_breached(state, now=at(2026, 8, 3, 9, 0)) is True


class TestWarnings:
    def test_threshold_is_a_fraction_of_the_way_to_due(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), at(2026, 8, 3, 14, 0), None, 0.0, None, None)
        threshold = warning_threshold_at(state, warning_percent=80)
        assert threshold == at(2026, 8, 3, 13, 12)

    def test_no_threshold_before_the_clock_has_started(self) -> None:
        state = ClockState(None, None, None, 0.0, None, None)
        assert warning_threshold_at(state, warning_percent=80) is None

    def test_should_warn_fires_at_and_after_the_threshold(self) -> None:
        state = ClockState(at(2026, 8, 3, 10, 0), at(2026, 8, 3, 14, 0), None, 0.0, None, None)
        assert should_warn(state, now=at(2026, 8, 3, 13, 12), warning_percent=80) is True
        assert should_warn(state, now=at(2026, 8, 3, 13, 11), warning_percent=80) is False

    def test_a_met_clock_never_warns(self) -> None:
        state = ClockState(
            at(2026, 8, 3, 10, 0),
            at(2026, 8, 3, 14, 0),
            None,
            0.0,
            at(2026, 8, 3, 10, 5),
            None,
        )
        assert should_warn(state, now=at(2026, 8, 3, 13, 30), warning_percent=80) is False


class TestPauseResume:
    def test_resume_returns_the_paused_duration(self) -> None:
        seconds = resume_paused_seconds(
            paused_at=at(2026, 8, 3, 10, 0), resumed_at=at(2026, 8, 3, 10, 15)
        )
        assert seconds == 900.0

    def test_resuming_before_pausing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must not precede"):
            resume_paused_seconds(
                paused_at=at(2026, 8, 3, 10, 15), resumed_at=at(2026, 8, 3, 10, 0)
            )


class TestComplianceRate:
    def test_all_met_is_one_hundred(self) -> None:
        assert compliance_rate(met=10, breached=0) == 100.0

    def test_all_breached_is_zero(self) -> None:
        assert compliance_rate(met=0, breached=10) == 0.0

    def test_a_mix_is_proportional(self) -> None:
        assert compliance_rate(met=3, breached=1) == 75.0

    def test_no_data_is_one_hundred_not_zero(self) -> None:
        # Zero measured SLAs is not evidence of failure.
        assert compliance_rate(met=0, breached=0) == 100.0
