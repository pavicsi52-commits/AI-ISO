"""Tests for dead-letter inspection, filtering, export, replay, and purge."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.queue.dead_letter import (
    dead_letter_queue_name_for,
    export_dead_letters,
    filter_dead_letters,
    inspect_dead_letters,
    purge_dead_letters,
    replay_dead_letters,
)
from shared_core.queue.exceptions import DeadLetterError
from shared_core.queue.manager import QueueManager


def _unique_queue_name() -> str:
    return f"deadletter.queue.test.{uuid.uuid4().hex}"


def test_dead_letter_queue_name_for_appends_the_suffix() -> None:
    assert dead_letter_queue_name_for("orders") == "orders.dlq"


async def _dead_letter_one_message(
    connection: AbstractRobustConnection, queue_name: str, payload: dict[str, object]
) -> None:
    """Publish one message whose handler always fails, so it lands on the DLQ."""
    queue_manager = QueueManager(connection)
    await queue_manager.declare_queue_with_dlq(queue_name)

    attempts: list[int] = []

    async def always_fails(message: dict[str, object]) -> None:
        attempts.append(1)
        raise ValueError("intentional failure for dead-letter test")

    await queue_manager.consume(queue_name, always_fails, max_retries=1)
    await queue_manager.publish(queue_name, payload)

    for _ in range(80):
        if len(attempts) >= 2:  # original attempt + 1 retry, then dead-lettered
            await (await queue_manager.channel()).close()
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"Handler only saw {len(attempts)} attempt(s); never exhausted retries.")


async def test_inspect_dead_letters_peeks_without_consuming(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 1})
    queue_manager = QueueManager(rabbitmq_connection)

    first_peek = await inspect_dead_letters(queue_manager, queue_name)
    second_peek = await inspect_dead_letters(queue_manager, queue_name)

    assert len(first_peek) == 1
    assert first_peek[0].payload == {"order_id": 1}
    assert len(second_peek) == 1  # still there


async def test_filter_dead_letters_returns_only_matching_messages(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 1, "urgent": True})
    queue_manager = QueueManager(rabbitmq_connection)

    matching = await filter_dead_letters(
        queue_manager, queue_name, lambda p: p.get("urgent") is True
    )
    non_matching = await filter_dead_letters(
        queue_manager, queue_name, lambda p: p.get("urgent") is False
    )

    assert len(matching) == 1
    assert non_matching == []


async def test_export_dead_letters_writes_a_json_file(
    rabbitmq_connection: AbstractRobustConnection, tmp_path: Path
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 42})
    queue_manager = QueueManager(rabbitmq_connection)
    destination = tmp_path / "dead_letters.json"

    count = await export_dead_letters(queue_manager, queue_name, destination)

    assert count == 1
    exported = json.loads(destination.read_text(encoding="utf-8"))
    assert exported == [{"order_id": 42}]
    # non-consuming
    assert len(await inspect_dead_letters(queue_manager, queue_name)) == 1


async def test_replay_dead_letters_moves_the_message_back_to_the_original_queue(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 7})
    queue_manager = QueueManager(rabbitmq_connection)

    replayed_count = await replay_dead_letters(queue_manager, queue_name)

    assert replayed_count == 1
    assert await inspect_dead_letters(queue_manager, queue_name) == []

    channel = await queue_manager.channel()
    original_queue = await channel.declare_queue(queue_name, durable=True, passive=True)
    assert original_queue.declaration_result.message_count == 1


async def test_purge_dead_letters_permanently_removes_messages(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 9})
    queue_manager = QueueManager(rabbitmq_connection)

    purged_count = await purge_dead_letters(queue_manager, queue_name)

    assert purged_count == 1
    assert await inspect_dead_letters(queue_manager, queue_name) == []


async def test_dead_letter_operations_with_limit_zero_touch_nothing(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_name = _unique_queue_name()
    await _dead_letter_one_message(rabbitmq_connection, queue_name, {"order_id": 3})
    queue_manager = QueueManager(rabbitmq_connection)

    assert await inspect_dead_letters(queue_manager, queue_name, limit=0) == []
    assert await replay_dead_letters(queue_manager, queue_name, limit=0) == 0
    assert await purge_dead_letters(queue_manager, queue_name, limit=0) == 0
    assert len(await inspect_dead_letters(queue_manager, queue_name)) == 1


async def test_inspect_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await inspect_dead_letters(queue_manager, _unique_queue_name())


async def test_replay_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await replay_dead_letters(queue_manager, _unique_queue_name())


async def test_purge_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await purge_dead_letters(queue_manager, _unique_queue_name())
