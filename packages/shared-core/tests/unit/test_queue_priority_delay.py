"""Tests for priority queues and delayed (TTL+DLX) requeuing."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.enums.priority import Priority
from shared_core.queue.delay import (
    declare_delay_queue,
    delay_queue_name_for,
    delay_until,
    validate_delay,
)
from shared_core.queue.exceptions import InvalidDelayError, InvalidPriorityError
from shared_core.queue.priority import declare_priority_queue, priority_level


def _unique(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex}"


# --- priority.py ---


def test_priority_level_covers_every_framework_level() -> None:
    assert priority_level(Priority.CRITICAL) == 9
    assert priority_level(Priority.HIGH) == 7
    assert priority_level(Priority.NORMAL) == 4
    assert priority_level(Priority.LOW) == 2
    assert priority_level(Priority.BACKGROUND) == 0


def test_priority_level_raises_for_an_unrecognized_value() -> None:
    with pytest.raises(InvalidPriorityError):
        priority_level("not-a-real-priority")  # type: ignore[arg-type]


async def test_declare_priority_queue_and_higher_priority_delivers_first(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq_connection.channel()
    queue_name = _unique("priority.queue")
    await declare_priority_queue(channel, queue_name)

    # Publish low-then-high while nothing is consuming yet, so both sit in
    # the queue together -- only then does priority ordering apply.
    await channel.default_exchange.publish(
        aio_pika.Message(body=b"low", priority=priority_level(Priority.LOW)),
        routing_key=queue_name,
    )
    await channel.default_exchange.publish(
        aio_pika.Message(body=b"critical", priority=priority_level(Priority.CRITICAL)),
        routing_key=queue_name,
    )

    queue = await channel.get_queue(queue_name)
    first = await queue.get(timeout=5)
    await first.ack()
    second = await queue.get(timeout=5)
    await second.ack()

    assert first.body == b"critical"
    assert second.body == b"low"


# --- delay.py ---


def test_delay_queue_name_for_is_deterministic() -> None:
    assert delay_queue_name_for("orders", 5000) == "orders.delay.5000"


def test_validate_delay_accepts_the_supported_range() -> None:
    validate_delay(0)
    validate_delay(1000)  # must not raise


def test_validate_delay_rejects_a_negative_delay() -> None:
    with pytest.raises(InvalidDelayError):
        validate_delay(-1)


def test_validate_delay_rejects_a_delay_beyond_the_maximum() -> None:
    with pytest.raises(InvalidDelayError):
        validate_delay(1000 * 60 * 60 * 24 * 8)  # 8 days


def test_delay_until_computes_milliseconds_from_now() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    target = now + timedelta(seconds=5)

    assert delay_until(target, now=now) == 5000


def test_delay_until_rejects_a_target_in_the_past() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    target = now - timedelta(seconds=5)

    with pytest.raises(InvalidDelayError):
        delay_until(target, now=now)


async def test_declare_delay_queue_dead_letters_back_to_the_real_queue_after_ttl(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq_connection.channel()
    real_queue_name = _unique("delay.target")
    await channel.declare_queue(real_queue_name, durable=True)

    holding_name = await declare_delay_queue(channel, real_queue_name, 300)
    assert holding_name == delay_queue_name_for(real_queue_name, 300)

    await channel.default_exchange.publish(
        aio_pika.Message(body=b"delayed-hello"), routing_key=holding_name
    )

    real_queue = await channel.get_queue(real_queue_name)
    message = None
    for _ in range(30):
        message = await real_queue.get(fail=False, timeout=0.5)
        if message is not None:
            break
        await asyncio.sleep(0.1)

    assert message is not None
    assert message.body == b"delayed-hello"
    await message.ack()
