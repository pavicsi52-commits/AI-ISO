"""Tests for worker.py, against the real RabbitMQ started by docker-compose.yml."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.enums.job_status import JobStatus
from shared_core.queue.manager import QueueManager
from shared_core.queue.retry import RetryPolicy
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.executor import ExecutionResult, JobExecutor
from shared_core.scheduler.heartbeat import HeartbeatRegistry, HeartbeatSender
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.queue import JobQueue
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType
from shared_core.scheduler.worker import Worker


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


def _queue_name() -> str:
    return f"scheduler.worker-test.{uuid.uuid4().hex}"


async def test_worker_executes_a_due_job_and_marks_it_completed(
    queue_manager: QueueManager,
) -> None:
    ran = asyncio.Event()

    async def fn(_job: Job) -> None:
        ran.set()

    job = build_job(
        job_name="worker-test-job",
        job_type=JobType.BACKGROUND,
        fn=fn,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
    )
    registry = JobRegistry()
    registry.register(job)
    engine = SchedulerEngine(registry)
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    worker = Worker("node-a", registry, engine, job_queue, JobExecutor())

    await worker.start()
    await job_queue.enqueue(job.job_id)
    await asyncio.wait_for(ran.wait(), timeout=5)
    for _ in range(50):
        if registry.get(job.job_id).status == JobStatus.COMPLETED:
            break
        await asyncio.sleep(0.05)

    assert registry.get(job.job_id).status == JobStatus.COMPLETED
    await worker.stop()


async def test_worker_marks_a_failing_job_as_failed(queue_manager: QueueManager) -> None:
    async def fn(_job: Job) -> None:
        raise RuntimeError("boom")

    job = build_job(
        job_name="worker-failing-job",
        job_type=JobType.BACKGROUND,
        fn=fn,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    registry = JobRegistry()
    registry.register(job)
    engine = SchedulerEngine(registry)
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    worker = Worker("node-a", registry, engine, job_queue, JobExecutor())

    await worker.start()
    await job_queue.enqueue(job.job_id)
    for _ in range(50):
        if registry.get(job.job_id).status == JobStatus.FAILED:
            break
        await asyncio.sleep(0.05)

    assert registry.get(job.job_id).status == JobStatus.FAILED
    await worker.stop()


async def test_worker_drops_an_unknown_job_id_without_raising(
    queue_manager: QueueManager, caplog: pytest.LogCaptureFixture
) -> None:
    registry = JobRegistry()
    engine = SchedulerEngine(registry)
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    worker = Worker("node-a", registry, engine, job_queue, JobExecutor())

    await worker.start()
    with caplog.at_level("WARNING"):
        await job_queue.enqueue("does-not-exist")
        await asyncio.sleep(0.5)

    assert "unknown job id" in caplog.text
    await worker.stop()


async def test_worker_starts_and_stops_its_heartbeat_when_configured(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    registry = JobRegistry()
    engine = SchedulerEngine(registry)
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    heartbeat_registry = HeartbeatRegistry(redis_client)
    sender = HeartbeatSender(heartbeat_registry, "node-a", interval_seconds=10)
    worker = Worker("node-a", registry, engine, job_queue, JobExecutor(), heartbeat=sender)

    await worker.start()
    assert await heartbeat_registry.is_alive("node-a") is True

    await worker.stop()
    assert await heartbeat_registry.is_alive("node-a") is False


async def test_worker_leaves_status_alone_when_the_handler_reports_zero_attempts(
    queue_manager: QueueManager,
) -> None:
    async def _noop(_job: Job) -> None:
        pass

    job = build_job(
        job_name="worker-skipped-job",
        job_type=JobType.BACKGROUND,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
    )
    registry = JobRegistry()
    registry.register(job)
    engine = SchedulerEngine(registry)
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()

    async def skipped_handler(handled_job: Job) -> ExecutionResult:
        now = datetime.now(UTC)
        return ExecutionResult(
            job_id=handled_job.job_id,
            succeeded=False,
            attempts=0,
            started_at=now,
            finished_at=now,
            error="Denied by a middleware.",
        )

    worker = Worker("node-a", registry, engine, job_queue, JobExecutor(), handler=skipped_handler)

    await worker.start()
    await job_queue.enqueue(job.job_id)
    await asyncio.sleep(0.5)

    assert registry.get(job.job_id).status == JobStatus.RUNNING
    await worker.stop()
