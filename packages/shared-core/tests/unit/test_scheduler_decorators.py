"""Tests for decorators.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.scheduler.decorators import (
    build_job_from_decorated,
    cron,
    delay,
    exclusive,
    interval,
    once,
    retryable,
    scheduled,
    timeout,
)
from shared_core.scheduler.job import Job, JobType
from shared_core.scheduler.schedule import Schedule, ScheduleType


async def _noop(_job: Job) -> None:
    pass


def test_cron_sets_a_cron_expression_schedule() -> None:
    @cron("0 2 * * *")
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="nightly", job_type=JobType.REPORT)

    assert job.schedule.schedule_type == ScheduleType.CRON_EXPRESSION
    assert job.schedule.cron_expression == "0 2 * * *"


def test_interval_sets_a_fixed_rate_schedule() -> None:
    @interval(30)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="poll", job_type=JobType.MONITORING)

    assert job.schedule.schedule_type == ScheduleType.FIXED_RATE
    assert job.schedule.interval == timedelta(seconds=30)


def test_delay_sets_a_fixed_delay_schedule() -> None:
    @delay(15)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="retry-cleanup", job_type=JobType.CLEANUP)

    assert job.schedule.schedule_type == ScheduleType.FIXED_DELAY
    assert job.schedule.delay == timedelta(seconds=15)


def test_once_without_run_at_is_immediate() -> None:
    @once()
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="one-shot", job_type=JobType.BACKGROUND)

    assert job.schedule.schedule_type == ScheduleType.IMMEDIATE


def test_once_with_run_at_is_scheduled_time() -> None:
    run_at = datetime(2026, 12, 25, tzinfo=UTC)

    @once(run_at=run_at)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="holiday-job", job_type=JobType.BACKGROUND)

    assert job.schedule.schedule_type == ScheduleType.SCHEDULED_TIME
    assert job.schedule.run_at == run_at


def test_scheduled_accepts_an_arbitrary_schedule() -> None:
    custom = Schedule(schedule_type=ScheduleType.EVENT_TRIGGERED, event_name="order.created")

    @scheduled(custom)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="on-order", job_type=JobType.AUTOMATION)

    assert job.schedule is custom


def test_retryable_sets_the_retry_policy() -> None:
    @retryable(max_attempts=7, backoff_base_seconds=0.5, backoff_max_seconds=10.0)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="flaky", job_type=JobType.BACKGROUND)

    assert job.retry_policy.max_attempts == 7
    assert job.retry_policy.backoff_base_seconds == 0.5
    assert job.retry_policy.backoff_max_seconds == 10.0


def test_retryable_defaults_backoff_when_not_given() -> None:
    @retryable(max_attempts=2)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="flaky", job_type=JobType.BACKGROUND)

    assert job.retry_policy.max_attempts == 2


def test_timeout_sets_the_timeout_seconds() -> None:
    @timeout(45.0)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="slow-task", job_type=JobType.BACKGROUND)

    assert job.timeout_seconds == 45.0


def test_exclusive_sets_metadata_flag() -> None:
    @exclusive
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="single-runner", job_type=JobType.BACKGROUND)

    assert job.metadata["exclusive"] is True


def test_decorators_stack() -> None:
    @exclusive
    @timeout(10.0)
    @retryable(max_attempts=5)
    @cron("*/5 * * * *")
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="combined", job_type=JobType.BACKGROUND)

    assert job.schedule.schedule_type == ScheduleType.CRON_EXPRESSION
    assert job.retry_policy.max_attempts == 5
    assert job.timeout_seconds == 10.0
    assert job.metadata["exclusive"] is True


def test_build_job_from_decorated_defaults_to_immediate_with_no_decorators() -> None:
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(task, job_name="bare", job_type=JobType.BACKGROUND)

    assert job.schedule.schedule_type == ScheduleType.IMMEDIATE


def test_build_job_from_decorated_overrides_win_over_decorator_metadata() -> None:
    @timeout(10.0)
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(
        task, job_name="override", job_type=JobType.BACKGROUND, timeout_seconds=99.0
    )

    assert job.timeout_seconds == 99.0


def test_build_job_from_decorated_merges_explicit_metadata_with_exclusive_flag() -> None:
    @exclusive
    async def task(_job: Job) -> None:
        pass

    job = build_job_from_decorated(
        task, job_name="merged", job_type=JobType.BACKGROUND, metadata={"custom": "value"}
    )

    assert job.metadata == {"custom": "value", "exclusive": True}
