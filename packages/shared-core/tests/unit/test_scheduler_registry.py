"""Tests for registry.py."""

from __future__ import annotations

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.exceptions import JobNotFoundError
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType


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


def test_register_then_get_round_trips() -> None:
    registry = JobRegistry()
    job = _job()

    registry.register(job)

    assert registry.get(job.job_id) is job


def test_get_raises_for_an_unregistered_job() -> None:
    registry = JobRegistry()

    with pytest.raises(JobNotFoundError):
        registry.get("missing")


def test_unregister_removes_the_job() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    registry.unregister(job.job_id)

    with pytest.raises(JobNotFoundError):
        registry.get(job.job_id)


def test_unregister_unknown_job_is_a_no_op() -> None:
    registry = JobRegistry()

    registry.unregister("missing")


def test_status_of_returns_none_for_an_unregistered_job() -> None:
    registry = JobRegistry()

    assert registry.status_of("missing") is None


def test_status_of_returns_the_registered_jobs_status() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    assert registry.status_of(job.job_id) == JobStatus.REGISTERED


def test_list_jobs_returns_every_registered_job() -> None:
    registry = JobRegistry()
    job_a, job_b = _job(), _job()
    registry.register(job_a)
    registry.register(job_b)

    assert {job.job_id for job in registry.list_jobs()} == {job_a.job_id, job_b.job_id}


def test_list_by_status_filters() -> None:
    registry = JobRegistry()
    job_a, job_b = _job(), _job()
    registry.register(job_a)
    registry.register(job_b)
    registry.pause(job_b.job_id)

    assert [job.job_id for job in registry.list_by_status(JobStatus.PAUSED)] == [job_b.job_id]


def test_transition_updates_status_and_updated_at() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    updated = registry.transition(job.job_id, JobStatus.RUNNING)

    assert updated.status == JobStatus.RUNNING
    assert updated.updated_at >= job.updated_at


def test_transition_applies_extra_field_updates() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    updated = registry.transition(job.job_id, JobStatus.RUNNING, owner="ops")

    assert updated.owner == "ops"


def test_transition_raises_for_an_unregistered_job() -> None:
    registry = JobRegistry()

    with pytest.raises(JobNotFoundError):
        registry.transition("missing", JobStatus.RUNNING)


def test_pause_resume_cancel() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    assert registry.pause(job.job_id).status == JobStatus.PAUSED
    assert registry.resume(job.job_id).status == JobStatus.SCHEDULED
    assert registry.cancel(job.job_id).status == JobStatus.CANCELLED


@pytest.mark.parametrize("status", [JobStatus.CANCELLED, JobStatus.EXPIRED, JobStatus.ARCHIVED])
def test_is_terminal_true_for_terminal_statuses(status: JobStatus) -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)
    registry.transition(job.job_id, status)

    assert registry.is_terminal(job.job_id) is True


def test_is_terminal_false_for_a_non_terminal_status() -> None:
    registry = JobRegistry()
    job = _job()
    registry.register(job)

    assert registry.is_terminal(job.job_id) is False


def test_is_terminal_raises_for_an_unregistered_job() -> None:
    registry = JobRegistry()

    with pytest.raises(JobNotFoundError):
        registry.is_terminal("missing")
