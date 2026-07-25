"""Tests for the RabbitMQ queue framework.

Runs against the real RabbitMQ started by the repository's
``docker-compose.yml`` (Phase 1) rather than a mock, for genuine
integration confidence. Skipped automatically if RabbitMQ is unreachable
(see the ``rabbitmq_connection``/``queue_manager`` fixtures in conftest.py).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from shared_core.queue import QueueManager, WorkerBase
from shared_core.queue.retry import RetryPolicy


def _unique_queue_name() -> str:
    return f"test.{uuid.uuid4().hex}"


async def test_declare_queue_with_dlq_returns_both_names(queue_manager: QueueManager) -> None:
    queue_name = _unique_queue_name()

    declared, dlq = await queue_manager.declare_queue_with_dlq(queue_name)

    assert declared == queue_name
    assert dlq == f"{queue_name}.dlq"


async def test_publish_and_consume_round_trip(queue_manager: QueueManager) -> None:
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await queue_manager.consume(queue_name, handler)
    await queue_manager.publish(queue_name, {"hello": "world"})

    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)

    assert received == [{"hello": "world"}]


async def test_failed_message_is_retried_then_dead_lettered(queue_manager: QueueManager) -> None:
    queue_name = _unique_queue_name()
    _, dlq_name = await queue_manager.declare_queue_with_dlq(queue_name)

    attempts: list[int] = []

    async def always_fails(message: dict[str, Any]) -> None:
        attempts.append(1)
        raise RuntimeError("simulated failure")

    await queue_manager.consume(queue_name, always_fails, max_retries=2)
    await queue_manager.publish(queue_name, {"payload": "x"})

    for _ in range(80):
        if len(attempts) >= 3:
            break
        await asyncio.sleep(0.1)

    assert len(attempts) == 3  # initial attempt + 2 retries

    channel = await queue_manager.channel()
    dlq = await channel.get_queue(dlq_name)
    dead_message = await dlq.get(timeout=5, fail=False)
    assert dead_message is not None


async def test_publish_records_failed_and_reraises_on_a_broker_error(
    queue_manager: QueueManager,
) -> None:
    class _ExplodingExchange:
        async def publish(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated broker rejection")

    class _ExplodingChannel:
        default_exchange = _ExplodingExchange()
        is_closed = False

    queue_manager._channel = _ExplodingChannel()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="simulated broker rejection"):
        await queue_manager.publish("some.queue", {"x": 1})

    assert queue_manager.statistics.failed == 1


async def test_retry_with_a_sub_second_backoff_requeues_immediately_without_a_delay_queue(
    queue_manager: QueueManager,
) -> None:
    """A backoff under 0.5s rounds to 0ms, taking the immediate-requeue branch
    rather than creating a delay-holding queue.
    """
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)

    attempts: list[int] = []

    async def always_fails(message: dict[str, Any]) -> None:
        attempts.append(1)
        raise RuntimeError("simulated failure")

    policy = RetryPolicy(max_attempts=1, backoff_base_seconds=0.1, backoff_max_seconds=1.0)
    await queue_manager.consume(queue_name, always_fails, retry_policy=policy)
    await queue_manager.publish(queue_name, {"payload": "x"})

    for _ in range(50):
        if len(attempts) >= 2:
            break
        await asyncio.sleep(0.1)

    # initial attempt (retry_count=0 < max_attempts=1, retries once with a
    # 0ms/immediate-requeue backoff) + 1 retry, then dead-lettered
    assert len(attempts) == 2


class _EchoWorker(WorkerBase):
    def __init__(self, queue_manager: QueueManager, queue_name: str) -> None:
        super().__init__(queue_manager)
        self.queue_name = queue_name
        self.received: list[dict[str, Any]] = []

    async def handle(self, message: dict[str, Any]) -> None:
        self.received.append(message)


async def test_worker_base_declares_queue_and_consumes(queue_manager: QueueManager) -> None:
    queue_name = _unique_queue_name()
    worker = _EchoWorker(queue_manager, queue_name)

    await worker.start()
    await queue_manager.publish(queue_name, {"worker": "test"})

    for _ in range(50):
        if worker.received:
            break
        await asyncio.sleep(0.1)

    assert worker.received == [{"worker": "test"}]
