"""Tests for helpers.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.helpers import format_duration, is_due, job_summary
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.schedule import Schedule, ScheduleType

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _noop(_job: Job) -> None:
    pass


def _job(**overrides: object) -> Job:
    return build_job(
        job_name="test-job",
        job_type=JobType.BACKGROUND,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        **overrides,
    )


def test_format_duration_seconds_only() -> None:
    assert format_duration(42) == "42s"


def test_format_duration_minutes_and_seconds() -> None:
    assert format_duration(150) == "2m 30s"


def test_format_duration_whole_minutes() -> None:
    assert format_duration(120) == "2m"


def test_format_duration_hours_and_minutes() -> None:
    assert format_duration(3900) == "1h 5m"


def test_format_duration_whole_hours() -> None:
    assert format_duration(7200) == "2h"


def test_is_due_false_without_a_next_run() -> None:
    job = _job(status=JobStatus.SCHEDULED, next_run=None)

    assert is_due(job, now=_NOW) is False


def test_is_due_false_when_next_run_is_in_the_future() -> None:
    job = _job(status=JobStatus.SCHEDULED, next_run=_NOW + timedelta(hours=1))

    assert is_due(job, now=_NOW) is False


def test_is_due_true_when_next_run_has_arrived() -> None:
    job = _job(status=JobStatus.SCHEDULED, next_run=_NOW)

    assert is_due(job, now=_NOW) is True


def test_is_due_false_for_a_non_due_status() -> None:
    job = _job(status=JobStatus.PAUSED, next_run=_NOW)

    assert is_due(job, now=_NOW) is False


def test_is_due_true_for_retrying_status() -> None:
    job = _job(status=JobStatus.RETRYING, next_run=_NOW)

    assert is_due(job, now=_NOW) is True


def test_job_summary_omits_fn_and_is_json_shaped() -> None:
    job = _job(next_run=_NOW, last_run=None)

    summary = job_summary(job)

    assert summary["job_id"] == job.job_id
    assert summary["job_name"] == "test-job"
    assert summary["status"] == JobStatus.REGISTERED.value
    assert summary["next_run"] == _NOW.isoformat()
    assert summary["last_run"] is None
    assert "fn" not in summary
