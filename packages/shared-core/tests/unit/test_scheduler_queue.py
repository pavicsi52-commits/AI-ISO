"""Tests for queue.py, against the real RabbitMQ started by docker-compose.yml."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from shared_core.queue.manager import QueueManager
from shared_core.scheduler.queue import (
    JobQueue,
    build_due_job_message,
    job_id_from_message,
)


def _queue_name() -> str:
    return f"scheduler.due-jobs.test.{uuid.uuid4().hex}"


def test_build_due_job_message_carries_the_job_id() -> None:
    message = build_due_job_message("job-1")

    assert message["job_id"] == "job-1"
    assert "enqueued_at" in message


def test_job_id_from_message_round_trips() -> None:
    message = build_due_job_message("job-1")

    assert job_id_from_message(message) == "job-1"


async def test_job_queue_enqueue_and_consume_round_trip(queue_manager: QueueManager) -> None:
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    received: asyncio.Queue[str] = asyncio.Queue()

    async def handler(job_id: str) -> None:
        await received.put(job_id)

    await job_queue.consume(handler)
    await job_queue.enqueue("job-42")

    job_id = await asyncio.wait_for(received.get(), timeout=5)
    assert job_id == "job-42"


async def test_job_queue_enqueue_at_delivers_after_the_delay(queue_manager: QueueManager) -> None:
    job_queue = JobQueue(queue_manager, queue_name=_queue_name())
    await job_queue.declare()
    received: asyncio.Queue[str] = asyncio.Queue()

    async def handler(job_id: str) -> None:
        await received.put(job_id)

    await job_queue.consume(handler)
    await job_queue.enqueue_at("job-later", at=datetime.now(UTC) + timedelta(seconds=1))

    job_id = await asyncio.wait_for(received.get(), timeout=10)
    assert job_id == "job-later"
