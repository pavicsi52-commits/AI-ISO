"""Tests for the Producer and Consumer ergonomic facades over QueueManager."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.enums.priority import Priority
from shared_core.queue.consumer import Consumer
from shared_core.queue.exceptions import PublishFailedError
from shared_core.queue.manager import QueueManager
from shared_core.queue.priority import declare_priority_queue
from shared_core.queue.producer import Producer
from shared_core.queue.retry import RetryPolicy


def _unique_queue_name() -> str:
    return f"producer.consumer.test.{uuid.uuid4().hex}"


async def _wait_until(predicate: object, *, attempts: int = 50, interval: float = 0.1) -> None:
    for _ in range(attempts):
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(interval)


# --- Producer ---


async def test_producer_publish_round_trips_through_a_consumer(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    producer = Producer(queue_manager)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await queue_manager.consume(queue_name, handler)
    await producer.publish(queue_name, {"hello": "producer"})

    await _wait_until(lambda: bool(received))
    assert received == [{"hello": "producer"}]


async def test_producer_publish_with_priority(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    channel = await queue_manager.channel()
    await declare_priority_queue(channel, queue_name)
    producer = Producer(queue_manager)

    await producer.publish(queue_name, {"level": "low"}, priority=Priority.LOW)
    await producer.publish(queue_name, {"level": "critical"}, priority=Priority.CRITICAL)

    queue = await channel.get_queue(queue_name)
    first = await queue.get(timeout=5)
    await first.ack()

    assert json.loads(first.body)["level"] == "critical"


async def test_producer_publish_batch_publishes_every_message_in_order(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    producer = Producer(queue_manager)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await queue_manager.consume(queue_name, handler)
    await producer.publish_batch(queue_name, [{"i": i} for i in range(3)])

    await _wait_until(lambda: len(received) >= 3)
    assert [item["i"] for item in received] == [0, 1, 2]


async def test_producer_publish_async_schedules_a_task_that_completes(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    producer = Producer(queue_manager)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await queue_manager.consume(queue_name, handler)
    task = producer.publish_async(queue_name, {"async": True})
    await task

    assert task.done()
    await _wait_until(lambda: bool(received))
    assert received == [{"async": True}]


async def test_producer_publish_scheduled_becomes_available_after_the_delay(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    channel = await queue_manager.channel()
    await channel.declare_queue(queue_name, durable=True)
    producer = Producer(queue_manager)

    at = datetime.now(UTC) + timedelta(milliseconds=300)
    await producer.publish_scheduled(queue_name, {"scheduled": True}, at=at)

    queue = await channel.get_queue(queue_name)
    message = None
    for _ in range(30):
        message = await queue.get(fail=False, timeout=0.3)
        if message is not None:
            break
        await asyncio.sleep(0.1)
    assert message is not None
    await message.ack()


async def test_producer_publish_raises_publish_failed_error_after_exhausting_retries() -> None:
    class _ExplodingQueueManager:
        async def publish(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("broker unreachable")

    policy = RetryPolicy(max_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    producer = Producer(_ExplodingQueueManager(), retry_policy=policy)  # type: ignore[arg-type]

    with pytest.raises(PublishFailedError):
        await producer.publish("some.queue", {"x": 1})


async def test_producer_publish_respects_a_timeout() -> None:
    class _SlowQueueManager:
        async def publish(self, *args: object, **kwargs: object) -> None:
            await asyncio.sleep(5)

    producer = Producer(_SlowQueueManager())  # type: ignore[arg-type]

    with pytest.raises(PublishFailedError, match="timed out"):
        await producer.publish("some.queue", {"x": 1}, timeout_seconds=0.1)


# --- Consumer ---


async def test_consumer_subscribe_filters_out_non_matching_messages(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    consumer = Consumer(queue_manager)
    producer = Producer(queue_manager)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await consumer.subscribe(queue_name, handler, filter=lambda m: m.get("keep") is True)
    await producer.publish(queue_name, {"keep": False})
    await producer.publish(queue_name, {"keep": True})

    await _wait_until(lambda: bool(received))
    await asyncio.sleep(0.3)  # give the filtered-out message a chance to (not) arrive
    assert received == [{"keep": True}]


async def test_consumer_subscribe_batch_flushes_at_batch_size(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    consumer = Consumer(queue_manager)
    producer = Producer(queue_manager)

    batches: list[list[dict[str, Any]]] = []

    async def handler(batch: list[dict[str, Any]]) -> None:
        batches.append(batch)

    await consumer.subscribe_batch(queue_name, handler, batch_size=3, flush_interval_seconds=5.0)
    for i in range(3):
        await producer.publish(queue_name, {"i": i})

    await _wait_until(lambda: bool(batches))
    assert len(batches[0]) == 3


async def test_consumer_subscribe_batch_flushes_on_the_interval_when_short_of_batch_size(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await queue_manager.declare_queue_with_dlq(queue_name)
    consumer = Consumer(queue_manager)
    producer = Producer(queue_manager)

    batches: list[list[dict[str, Any]]] = []

    async def handler(batch: list[dict[str, Any]]) -> None:
        batches.append(batch)

    await consumer.subscribe_batch(queue_name, handler, batch_size=10, flush_interval_seconds=0.3)
    await producer.publish(queue_name, {"only": "one"})

    await _wait_until(lambda: bool(batches), attempts=30, interval=0.1)
    assert batches == [[{"only": "one"}]]
