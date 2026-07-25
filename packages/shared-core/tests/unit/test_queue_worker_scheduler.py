"""Tests for the WorkerPool and TaskScheduler."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.queue.exceptions import SchedulingError, WorkerPoolError
from shared_core.queue.manager import QueueManager
from shared_core.queue.scheduler import ScheduledTask, TaskScheduler, next_run_time, validate_cron
from shared_core.queue.worker import WorkerBase, WorkerPool


def _unique_queue_name() -> str:
    return f"worker.test.{uuid.uuid4().hex}"


class _EchoWorker(WorkerBase):
    def __init__(self, queue_manager: QueueManager, queue_name: str) -> None:
        super().__init__(queue_manager)
        self.queue_name = queue_name
        self.received: list[dict[str, Any]] = []

    async def handle(self, message: dict[str, Any]) -> None:
        self.received.append(message)


class _AlwaysCrashesWorker(WorkerBase):
    queue_name = "unused"

    async def handle(self, message: dict[str, Any]) -> None:  # pragma: no cover -- never consumed
        pass

    async def start(self) -> None:
        raise RuntimeError("worker setup always fails")


# --- WorkerPool ---


def test_worker_pool_rejects_invalid_bounds() -> None:
    with pytest.raises(WorkerPoolError):
        WorkerPool(lambda: _AlwaysCrashesWorker(None), name="bad", min_workers=5, max_workers=2)  # type: ignore[arg-type]


async def test_worker_pool_starts_min_workers_and_reports_worker_count(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    workers: list[_EchoWorker] = []

    def factory() -> _EchoWorker:
        worker = _EchoWorker(queue_manager, queue_name)
        workers.append(worker)
        return worker

    pool = WorkerPool(factory, name="echo-pool", min_workers=2, max_workers=4)
    try:
        await pool.start()
        await asyncio.sleep(0.2)

        assert pool.worker_count == 2
        statuses = pool.status()
        assert len(statuses) == 2
        assert all(status.running for status in statuses)
    finally:
        await pool.shutdown()


async def test_worker_pool_scale_to_adds_and_removes_workers(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()

    def factory() -> _EchoWorker:
        return _EchoWorker(queue_manager, queue_name)

    pool = WorkerPool(factory, name="scale-pool", min_workers=1, max_workers=5)
    try:
        await pool.start()
        await pool.scale_to(3)
        assert pool.worker_count == 3

        await pool.scale_to(1)
        assert pool.worker_count == 1
    finally:
        await pool.shutdown()


async def test_worker_pool_scale_to_rejects_out_of_bounds_counts(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    pool = WorkerPool(
        lambda: _EchoWorker(queue_manager, queue_name),
        name="bounds-pool",
        min_workers=1,
        max_workers=2,
    )
    try:
        await pool.start()
        with pytest.raises(WorkerPoolError):
            await pool.scale_to(10)
    finally:
        await pool.shutdown()


async def test_worker_pool_restarts_a_crashing_worker() -> None:
    pool = WorkerPool(
        _AlwaysCrashesWorker,  # type: ignore[arg-type]
        name="crash-pool",
        min_workers=1,
        max_workers=1,
        restart_backoff_seconds=0.05,
    )
    try:
        await pool.start()
        await asyncio.sleep(0.3)

        statuses = pool.status()
        assert statuses[0].restart_count >= 1
    finally:
        await pool.shutdown()


async def test_worker_pool_shutdown_stops_every_worker(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    pool = WorkerPool(
        lambda: _EchoWorker(queue_manager, queue_name),
        name="shutdown-pool",
        min_workers=2,
        max_workers=2,
    )
    await pool.start()

    await pool.shutdown()

    assert pool.worker_count == 0
    assert pool.status() == []


# --- TaskScheduler ---


def test_validate_cron_accepts_a_valid_expression() -> None:
    validate_cron("*/5 * * * *")  # must not raise


def test_validate_cron_rejects_an_invalid_expression() -> None:
    with pytest.raises(SchedulingError):
        validate_cron("not a cron expression")


def test_next_run_time_returns_a_future_datetime() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    next_run = next_run_time("0 13 * * *", now=now)

    assert next_run == datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)


def test_scheduled_task_requires_a_cron_expression_or_run_at() -> None:
    with pytest.raises(SchedulingError):
        ScheduledTask(name="bad", fn=_noop)


def test_scheduled_task_validates_its_cron_expression_eagerly() -> None:
    with pytest.raises(SchedulingError):
        ScheduledTask(name="bad", fn=_noop, cron_expression="not valid")


async def _noop() -> None:
    pass


def test_task_scheduler_due_tasks_finds_a_past_due_one_shot_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = ScheduledTask(name="one-shot", fn=_noop, run_at=now - timedelta(seconds=1))
    scheduler.register(task)

    due = scheduler.due_tasks(now=now)

    assert due == [task]


def test_task_scheduler_due_tasks_excludes_a_future_one_shot_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    scheduler.register(ScheduledTask(name="future", fn=_noop, run_at=now + timedelta(hours=1)))

    assert scheduler.due_tasks(now=now) == []


def test_task_scheduler_due_tasks_excludes_a_disabled_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    scheduler.register(
        ScheduledTask(name="disabled", fn=_noop, run_at=now - timedelta(seconds=1), enabled=False)
    )

    assert scheduler.due_tasks(now=now) == []


def test_task_scheduler_finds_a_due_cron_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    task = ScheduledTask(name="every-minute", fn=_noop, cron_expression="* * * * *")
    scheduler.register(task)

    due = scheduler.due_tasks(now=now)

    assert due == [task]


def test_task_scheduler_unregister_removes_a_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    scheduler.register(ScheduledTask(name="temp", fn=_noop, run_at=now - timedelta(seconds=1)))

    scheduler.unregister("temp")

    assert scheduler.due_tasks(now=now) == []


async def test_task_scheduler_run_due_runs_and_records_due_tasks() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    calls: list[str] = []

    async def _record() -> None:
        calls.append("ran")

    scheduler.register(
        ScheduledTask(name="one-shot", fn=_record, run_at=now - timedelta(seconds=1))
    )

    ran_count = await scheduler.run_due(now=now)

    assert ran_count == 1
    assert calls == ["ran"]
    # a one-shot task that already ran is not due again
    assert await scheduler.run_due(now=now) == 0


async def test_task_scheduler_run_due_logs_and_continues_past_a_failing_task() -> None:
    scheduler = TaskScheduler()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    calls: list[str] = []

    async def _fails() -> None:
        raise RuntimeError("boom")

    async def _succeeds() -> None:
        calls.append("ran")

    scheduler.register(ScheduledTask(name="failing", fn=_fails, run_at=now - timedelta(seconds=1)))
    scheduler.register(ScheduledTask(name="ok", fn=_succeeds, run_at=now - timedelta(seconds=1)))

    ran_count = await scheduler.run_due(now=now)

    assert ran_count == 1
    assert calls == ["ran"]
