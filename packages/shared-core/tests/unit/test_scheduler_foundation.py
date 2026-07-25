"""Tests for schedule.py, job.py, retry.py, cron.py, timezone.py, and calendar.py."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.enums.priority import Priority
from shared_core.scheduler.calendar import CalendarRule, parse_calendar_rule
from shared_core.scheduler.cron import next_run_time, validate_cron
from shared_core.scheduler.exceptions import InvalidScheduleError
from shared_core.scheduler.job import Job, JobType, build_job, new_job_id
from shared_core.scheduler.retry import job_retry_policy
from shared_core.scheduler.schedule import Schedule, ScheduleType
from shared_core.scheduler.timezone import convert_timezone, localize, to_utc, validate_timezone

# --- schedule.py ---


def test_schedule_immediate_requires_no_extra_fields() -> None:
    Schedule(schedule_type=ScheduleType.IMMEDIATE)


def test_schedule_cron_expression_requires_a_cron_expression() -> None:
    with pytest.raises(InvalidScheduleError):
        Schedule(schedule_type=ScheduleType.CRON_EXPRESSION)


def test_schedule_cron_expression_with_the_field_set_succeeds() -> None:
    schedule = Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression="* * * * *")

    assert schedule.cron_expression == "* * * * *"


def test_schedule_scheduled_time_requires_run_at() -> None:
    with pytest.raises(InvalidScheduleError):
        Schedule(schedule_type=ScheduleType.SCHEDULED_TIME)


def test_schedule_type_covers_every_documented_type() -> None:
    expected = {
        "immediate",
        "scheduled_time",
        "cron_expression",
        "fixed_delay",
        "fixed_rate",
        "calendar_schedule",
        "business_hours",
        "maintenance_window",
        "event_triggered",
    }
    assert {schedule_type.value for schedule_type in ScheduleType} == expected


# --- job.py ---


def test_new_job_id_generates_unique_ids() -> None:
    assert new_job_id() != new_job_id()


async def _noop(_job: Job) -> None:
    pass


def test_build_job_defaults_priority_and_status() -> None:
    job = build_job(
        job_name="nightly-report",
        job_type=JobType.REPORT,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
    )

    assert job.priority == Priority.NORMAL
    assert job.status == JobStatus.REGISTERED
    assert job.job_id


def test_build_job_accepts_extra_fields() -> None:
    job = build_job(
        job_name="cleanup",
        job_type=JobType.CLEANUP,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        owner="ops-team",
        timezone="America/New_York",
    )

    assert job.owner == "ops-team"
    assert job.timezone == "America/New_York"


def test_job_type_covers_every_documented_type() -> None:
    expected = {
        "one_time",
        "recurring",
        "cron",
        "fixed_interval",
        "delayed",
        "workflow_timer",
        "maintenance",
        "background",
        "system",
        "automation",
        "validation",
        "monitoring",
        "ai",
        "cleanup",
        "backup",
        "import",
        "export",
        "report",
    }
    assert {job_type.value for job_type in JobType} == expected


# --- retry.py ---


def test_job_retry_policy_has_a_sensible_default() -> None:
    policy = job_retry_policy()

    assert policy.max_attempts == 3


# --- cron.py ---


def test_validate_cron_accepts_a_valid_expression() -> None:
    validate_cron("0 2 * * *")


def test_validate_cron_rejects_an_invalid_expression() -> None:
    with pytest.raises(InvalidScheduleError):
        validate_cron("not a cron expression")


def test_next_run_time_is_strictly_after_now() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    result = next_run_time("0 2 * * *", now=now)

    assert result > now


def test_next_run_time_rejects_an_invalid_expression() -> None:
    with pytest.raises(InvalidScheduleError):
        next_run_time("nonsense")


# --- timezone.py ---


def test_validate_timezone_accepts_a_real_timezone() -> None:
    validate_timezone("America/New_York")


def test_validate_timezone_rejects_an_unknown_timezone() -> None:
    with pytest.raises(InvalidScheduleError):
        validate_timezone("Not/A_Real_Zone")


def test_localize_attaches_the_given_timezone() -> None:
    naive = datetime(2026, 6, 1, 9, 0)

    localized = localize(naive, "America/New_York")

    assert localized.tzinfo is not None
    assert str(localized.tzinfo) == "America/New_York"


def test_to_utc_converts_a_naive_datetime() -> None:
    naive = datetime(2026, 6, 1, 9, 0)

    result = to_utc(naive, "America/New_York")

    assert result.tzinfo == UTC
    assert result.hour == 13  # EDT is UTC-4 in June


def test_convert_timezone_requires_an_aware_datetime() -> None:
    with pytest.raises(InvalidScheduleError):
        convert_timezone(datetime(2026, 6, 1, 9, 0), to="America/New_York")


def test_convert_timezone_converts_between_two_real_zones() -> None:
    utc_moment = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)

    result = convert_timezone(utc_moment, to="America/New_York")

    assert result.hour == 9  # EDT is UTC-4 in June


# --- calendar.py ---


def test_parse_calendar_rule_with_a_weekday_range() -> None:
    rule = parse_calendar_rule("MON-FRI 09:00-17:00")

    assert rule.weekdays == frozenset({0, 1, 2, 3, 4})
    assert rule.start_time == time(9, 0)
    assert rule.end_time == time(17, 0)


def test_parse_calendar_rule_with_a_weekday_list() -> None:
    rule = parse_calendar_rule("MON,WED,FRI 09:00-17:00")

    assert rule.weekdays == frozenset({0, 2, 4})


def test_parse_calendar_rule_rejects_a_malformed_rule() -> None:
    with pytest.raises(InvalidScheduleError):
        parse_calendar_rule("this is not valid")


def test_parse_calendar_rule_rejects_an_unknown_weekday() -> None:
    with pytest.raises(InvalidScheduleError):
        parse_calendar_rule("XXX 09:00-17:00")


def test_parse_calendar_rule_rejects_a_malformed_time_range() -> None:
    with pytest.raises(InvalidScheduleError):
        parse_calendar_rule("MON-FRI not-a-time")


def test_calendar_rule_is_active_within_the_window() -> None:
    rule = CalendarRule(
        weekdays=frozenset({0, 1, 2, 3, 4}), start_time=time(9, 0), end_time=time(17, 0)
    )
    monday_noon = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)  # a Monday

    assert rule.is_active(monday_noon) is True


def test_calendar_rule_is_inactive_outside_the_window() -> None:
    rule = CalendarRule(
        weekdays=frozenset({0, 1, 2, 3, 4}), start_time=time(9, 0), end_time=time(17, 0)
    )
    monday_late_evening = datetime(2026, 6, 1, 22, 0, tzinfo=UTC)

    assert rule.is_active(monday_late_evening) is False


def test_calendar_rule_is_inactive_on_a_non_matching_weekday() -> None:
    rule = CalendarRule(
        weekdays=frozenset({0, 1, 2, 3, 4}), start_time=time(9, 0), end_time=time(17, 0)
    )
    saturday_noon = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)  # a Saturday

    assert rule.is_active(saturday_noon) is False


def test_calendar_rule_handles_a_window_wrapping_midnight() -> None:
    rule = CalendarRule(weekdays=frozenset({0}), start_time=time(22, 0), end_time=time(6, 0))
    monday_23 = datetime(2026, 6, 1, 23, 0, tzinfo=UTC)

    assert rule.is_active(monday_23) is True
