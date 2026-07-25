"""Tests for executor.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.cache.locks import DistributedLock
from shared_core.queue.retry import RetryPolicy
from shared_core.scheduler.executor import ExecutionResult, JobExecutor
from shared_core.scheduler.job import Job, JobFn, JobType, build_job
from shared_core.scheduler.locking import job_lock_key
from shared_core.scheduler.schedule import Schedule, ScheduleType

_FAST_RETRY_POLICY = RetryPolicy(
    max_attempts=3, backoff_base_seconds=0.001, backoff_max_seconds=0.01
)


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


def _job(fn: JobFn, **overrides: object) -> Job:
    return build_job(
        job_name="test-job",
        job_type=JobType.BACKGROUND,
        fn=fn,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        retry_policy=_FAST_RETRY_POLICY,
        **overrides,
    )


async def test_execute_succeeds_on_the_first_attempt() -> None:
    async def fn(_job: Job) -> None:
        return None

    result = await JobExecutor().execute(_job(fn))

    assert result.succeeded is True
    assert result.attempts == 1
    assert result.error is None


async def test_execute_retries_and_eventually_succeeds() -> None:
    calls = 0

    async def fn(_job: Job) -> None:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient failure")

    result = await JobExecutor().execute(_job(fn))

    assert result.succeeded is True
    assert result.attempts == 2


async def test_execute_exhausts_retries_and_reports_failure() -> None:
    async def fn(_job: Job) -> None:
        raise RuntimeError("permanent failure")

    result = await JobExecutor().execute(_job(fn))

    assert result.succeeded is False
    assert result.attempts == _FAST_RETRY_POLICY.max_attempts
    assert result.error is not None
    assert "permanent failure" in result.error


async def test_execute_wraps_a_timeout() -> None:
    async def fn(_job: Job) -> None:
        await asyncio.sleep(10)

    job = _job(fn, timeout_seconds=0.01)

    result = await JobExecutor().execute(job)

    assert result.succeeded is False
    assert result.error is not None
    assert "timeout" in result.error.lower()


def test_duration_seconds_reflects_elapsed_time() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    result = ExecutionResult(
        job_id="job-1",
        succeeded=True,
        attempts=1,
        started_at=started,
        finished_at=started + timedelta(seconds=5),
    )

    assert result.duration_seconds == 5.0


async def test_execute_under_lock_runs_when_uncontended(redis_client: Redis) -> None:
    async def fn(_job: Job) -> None:
        return None

    executor = JobExecutor(lock_client=redis_client)

    result = await executor.execute(_job(fn))

    assert result.succeeded is True
    assert result.attempts == 1


async def test_execute_under_lock_skips_when_another_worker_holds_it(redis_client: Redis) -> None:
    async def fn(_job: Job) -> None:
        return None

    job = _job(fn)
    other_holder = DistributedLock(redis_client, job_lock_key(job.job_id))
    await other_holder.acquire()
    executor = JobExecutor(lock_client=redis_client)

    result = await executor.execute(job)

    assert result.succeeded is False
    assert result.attempts == 0
    assert result.error is not None
    assert "lock" in result.error.lower()
