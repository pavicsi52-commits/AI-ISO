"""Tests for engine.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.dependency import DependencyGraph, JobDependency
from shared_core.scheduler.engine import SchedulerEngine, compute_next_run
from shared_core.scheduler.exceptions import InvalidScheduleError
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)  # a Monday


async def _noop(_job: Job) -> None:
    pass


def _job(schedule: Schedule, **overrides: object) -> Job:
    return build_job(
        job_name="test-job", job_type=JobType.BACKGROUND, fn=_noop, schedule=schedule, **overrides
    )


# --- compute_next_run: IMMEDIATE ---


def test_immediate_first_run_is_now() -> None:
    schedule = Schedule(schedule_type=ScheduleType.IMMEDIATE)

    assert compute_next_run(schedule, now=_NOW) == _NOW


def test_immediate_has_no_second_run() -> None:
    schedule = Schedule(schedule_type=ScheduleType.IMMEDIATE)

    assert compute_next_run(schedule, now=_NOW, last_run=_NOW) is None


# --- compute_next_run: SCHEDULED_TIME ---


def test_scheduled_time_returns_run_at() -> None:
    run_at = _NOW + timedelta(hours=1)
    schedule = Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=run_at)

    assert compute_next_run(schedule, now=_NOW) == run_at


def test_scheduled_time_has_no_second_run() -> None:
    run_at = _NOW + timedelta(hours=1)
    schedule = Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=run_at)

    assert compute_next_run(schedule, now=_NOW, last_run=run_at) is None


def test_scheduled_time_defensively_rejects_a_missing_run_at() -> None:
    schedule = Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=_NOW)
    object.__setattr__(schedule, "run_at", None)

    with pytest.raises(InvalidScheduleError):
        compute_next_run(schedule, now=_NOW)


# --- compute_next_run: CRON_EXPRESSION ---


def test_cron_expression_computes_the_next_occurrence() -> None:
    schedule = Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression="0 2 * * *")

    result = compute_next_run(schedule, now=_NOW)

    assert result is not None
    assert result > _NOW


def test_cron_expression_defensively_rejects_a_missing_expression() -> None:
    schedule = Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression="0 2 * * *")
    object.__setattr__(schedule, "cron_expression", None)

    with pytest.raises(InvalidScheduleError):
        compute_next_run(schedule, now=_NOW)


# --- compute_next_run: FIXED_DELAY ---


def test_fixed_delay_measures_from_last_run() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(minutes=30))
    last_run = _NOW - timedelta(minutes=10)

    assert compute_next_run(schedule, now=_NOW, last_run=last_run) == last_run + timedelta(
        minutes=30
    )


def test_fixed_delay_measures_from_now_when_never_run() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(minutes=30))

    assert compute_next_run(schedule, now=_NOW) == _NOW + timedelta(minutes=30)


def test_fixed_delay_defensively_rejects_a_missing_delay() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(minutes=1))
    object.__setattr__(schedule, "delay", None)

    with pytest.raises(InvalidScheduleError):
        compute_next_run(schedule, now=_NOW)


# --- compute_next_run: FIXED_RATE ---


def test_fixed_rate_measures_from_last_run() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(minutes=30))
    last_run = _NOW - timedelta(minutes=10)

    assert compute_next_run(schedule, now=_NOW, last_run=last_run) == last_run + timedelta(
        minutes=30
    )


def test_fixed_rate_never_returns_a_moment_in_the_past() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(minutes=5))
    last_run = _NOW - timedelta(hours=1)

    assert compute_next_run(schedule, now=_NOW, last_run=last_run) == _NOW


def test_fixed_rate_defensively_rejects_a_missing_interval() -> None:
    schedule = Schedule(schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(minutes=1))
    object.__setattr__(schedule, "interval", None)

    with pytest.raises(InvalidScheduleError):
        compute_next_run(schedule, now=_NOW)


# --- compute_next_run: CALENDAR_SCHEDULE / BUSINESS_HOURS / MAINTENANCE_WINDOW ---


def test_calendar_schedule_returns_now_when_already_active() -> None:
    schedule = Schedule(
        schedule_type=ScheduleType.CALENDAR_SCHEDULE, calendar_rule="MON-FRI 09:00-17:00"
    )

    assert compute_next_run(schedule, now=_NOW) == _NOW


def test_business_hours_returns_the_next_active_window() -> None:
    saturday_noon = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    schedule = Schedule(
        schedule_type=ScheduleType.BUSINESS_HOURS, calendar_rule="MON-FRI 09:00-17:00"
    )

    result = compute_next_run(schedule, now=saturday_noon)

    assert result is not None
    assert result.weekday() == 0  # the following Monday
    assert result.hour == 9


def test_maintenance_window_without_a_calendar_rule_behaves_like_immediate() -> None:
    schedule = Schedule(schedule_type=ScheduleType.MAINTENANCE_WINDOW)

    assert compute_next_run(schedule, now=_NOW) == _NOW
    assert compute_next_run(schedule, now=_NOW, last_run=_NOW) is None


# --- compute_next_run: EVENT_TRIGGERED ---


def test_event_triggered_never_has_a_computed_next_run() -> None:
    schedule = Schedule(schedule_type=ScheduleType.EVENT_TRIGGERED, event_name="order.created")

    assert compute_next_run(schedule, now=_NOW) is None
    assert compute_next_run(schedule, now=_NOW, last_run=_NOW) is None


# --- SchedulerEngine ---


def test_schedule_initial_run_sets_status_and_next_run() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.IMMEDIATE))
    registry.register(job)
    engine = SchedulerEngine(registry)

    updated = engine.schedule_initial_run(job.job_id, now=_NOW)

    assert updated.status == JobStatus.SCHEDULED
    assert updated.next_run == _NOW


def test_due_jobs_returns_a_job_whose_next_run_has_arrived() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.IMMEDIATE))
    registry.register(job)
    engine = SchedulerEngine(registry)
    engine.schedule_initial_run(job.job_id, now=_NOW)

    assert [due.job_id for due in engine.due_jobs(now=_NOW)] == [job.job_id]


def test_due_jobs_excludes_a_job_whose_next_run_is_in_the_future() -> None:
    registry = JobRegistry()
    job = _job(
        Schedule(schedule_type=ScheduleType.SCHEDULED_TIME, run_at=_NOW + timedelta(hours=1))
    )
    registry.register(job)
    engine = SchedulerEngine(registry)
    engine.schedule_initial_run(job.job_id, now=_NOW)

    assert engine.due_jobs(now=_NOW) == []


def test_due_jobs_excludes_a_paused_job() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.IMMEDIATE))
    registry.register(job)
    engine = SchedulerEngine(registry)
    engine.schedule_initial_run(job.job_id, now=_NOW)
    registry.pause(job.job_id)

    assert engine.due_jobs(now=_NOW) == []


def test_due_jobs_excludes_a_job_with_unsatisfied_dependencies() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.IMMEDIATE))
    registry.register(job)
    dependencies = DependencyGraph()
    dependencies.add(JobDependency(job_id=job.job_id, depends_on_job_id="upstream"))
    engine = SchedulerEngine(registry, dependencies)
    engine.schedule_initial_run(job.job_id, now=_NOW)

    assert engine.due_jobs(now=_NOW) == []


def test_advance_marks_a_one_shot_job_completed() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.IMMEDIATE))
    registry.register(job)
    engine = SchedulerEngine(registry)
    engine.schedule_initial_run(job.job_id, now=_NOW)

    updated = engine.advance(job.job_id, completed_at=_NOW)

    assert updated.status == JobStatus.COMPLETED
    assert updated.next_run is None


def test_advance_reschedules_a_recurring_job() -> None:
    registry = JobRegistry()
    job = _job(Schedule(schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(minutes=10)))
    registry.register(job)
    engine = SchedulerEngine(registry)
    engine.schedule_initial_run(job.job_id, now=_NOW)

    updated = engine.advance(job.job_id, completed_at=_NOW)

    assert updated.status == JobStatus.SCHEDULED
    assert updated.next_run == _NOW + timedelta(minutes=10)
