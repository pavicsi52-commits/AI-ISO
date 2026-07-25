"""Tests for manager.py, against the real RabbitMQ started by docker-compose.yml."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.enums.job_status import JobStatus
from shared_core.queue.manager import QueueManager
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.executor import JobExecutor
from shared_core.scheduler.failover import FailoverCoordinator
from shared_core.scheduler.heartbeat import HeartbeatRegistry, HeartbeatSender
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.leader import LeaderElection
from shared_core.scheduler.manager import SchedulerManager, new_node_id
from shared_core.scheduler.queue import JobQueue
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


def _queue_name() -> str:
    return f"scheduler.manager-test.{uuid.uuid4().hex}"


async def _noop(_job: Job) -> None:
    pass


def _job(**overrides: object) -> Job:
    return build_job(
        job_name="manager-test-job",
        job_type=JobType.BACKGROUND,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
        **overrides,
    )


def _manager(
    queue_manager: QueueManager, *, leader: LeaderElection | None = None
) -> SchedulerManager:
    registry = JobRegistry()
    engine = SchedulerEngine(registry)
    queue = JobQueue(queue_manager, queue_name=_queue_name())
    executor = JobExecutor()
    return SchedulerManager(registry, engine, queue, executor, leader=leader)


def test_new_node_id_generates_unique_ids() -> None:
    assert new_node_id() != new_node_id()


def test_register_job_schedules_the_first_run(queue_manager: QueueManager) -> None:
    manager = _manager(queue_manager)

    updated = manager.register_job(_job())

    assert updated.status == JobStatus.SCHEDULED
    assert updated.next_run is not None


def test_pause_resume_cancel_job(queue_manager: QueueManager) -> None:
    manager = _manager(queue_manager)
    job = manager.register_job(_job())

    assert manager.pause_job(job.job_id).status == JobStatus.PAUSED
    assert manager.resume_job(job.job_id).status == JobStatus.SCHEDULED
    assert manager.cancel_job(job.job_id).status == JobStatus.CANCELLED


async def test_dispatch_due_jobs_without_leader_election_dispatches_freely(
    queue_manager: QueueManager,
) -> None:
    manager = _manager(queue_manager)
    await manager.queue.declare()
    job = manager.register_job(_job())

    dispatched = await manager.dispatch_due_jobs()

    assert dispatched == [job.job_id]
    assert manager.registry.get(job.job_id).status == JobStatus.QUEUED


async def test_dispatch_due_jobs_skips_when_not_leader(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    other = LeaderElection(redis_client, "node-b")
    await other.campaign()
    leader = LeaderElection(redis_client, "node-a")
    await leader.campaign()
    manager = _manager(queue_manager, leader=leader)
    await manager.queue.declare()
    manager.register_job(_job())

    dispatched = await manager.dispatch_due_jobs()

    assert dispatched == []


async def test_dispatch_due_jobs_dispatches_when_leader(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    leader = LeaderElection(redis_client, "node-a")
    await leader.campaign()
    manager = _manager(queue_manager, leader=leader)
    await manager.queue.declare()
    job = manager.register_job(_job())

    dispatched = await manager.dispatch_due_jobs()

    assert dispatched == [job.job_id]


async def test_full_lifecycle_executes_a_registered_job(queue_manager: QueueManager) -> None:
    ran = asyncio.Event()

    async def fn(_job: Job) -> None:
        ran.set()

    manager = _manager(queue_manager)
    job = build_job(
        job_name="lifecycle-job",
        job_type=JobType.BACKGROUND,
        fn=fn,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
    )
    manager.register_job(job)

    await manager.start()
    try:
        await asyncio.wait_for(ran.wait(), timeout=5)
        for _ in range(50):
            if manager.registry.get(job.job_id).status == JobStatus.COMPLETED:
                break
            await asyncio.sleep(0.05)
        assert manager.registry.get(job.job_id).status == JobStatus.COMPLETED
    finally:
        await manager.stop()


async def test_start_and_stop_drive_heartbeat_leader_and_failover(
    redis_client: Redis, queue_manager: QueueManager
) -> None:
    registry = JobRegistry()
    engine = SchedulerEngine(registry)
    queue = JobQueue(queue_manager, queue_name=_queue_name())
    executor = JobExecutor()
    heartbeat_registry = HeartbeatRegistry(redis_client)
    node_id = "node-full-lifecycle"
    heartbeat = HeartbeatSender(heartbeat_registry, node_id, interval_seconds=10)
    leader = LeaderElection(redis_client, node_id, renew_interval_seconds=10)

    async def _on_node_failed(_node_id: str) -> None:
        pass

    failover = FailoverCoordinator(heartbeat_registry, _on_node_failed, poll_interval_seconds=10)
    manager = SchedulerManager(
        registry,
        engine,
        queue,
        executor,
        node_id=node_id,
        heartbeat=heartbeat,
        leader=leader,
        failover=failover,
    )

    await manager.start()
    assert await heartbeat_registry.is_alive(node_id) is True

    await manager.stop()
    assert await heartbeat_registry.is_alive(node_id) is False
