"""Tests for retry backoff classification and dead-letter inspection/replay/purge
against the real RabbitMQ started by the repository's docker-compose.yml.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import ClassVar

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.events.base import BaseEvent
from shared_core.events.constants import DEFAULT_RETRY_BACKOFF_MAX_SECONDS
from shared_core.events.dead_letter import (
    inspect_dead_letters,
    purge_dead_letters,
    replay_dead_letters,
)
from shared_core.events.exceptions import DeadLetterError, EventPublishFailedError
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry
from shared_core.events.retry import RetryPolicy, compute_backoff_delay, is_retryable
from shared_core.events.subscriber import EventSubscriber
from shared_core.exceptions.event import EventError
from shared_core.queue.manager import QueueManager


class _RetryableFrameworkError(EventError):
    error_code = "AIIOS-EVENT-9001"
    retryable = True


class _FatalFrameworkError(EventError):
    error_code = "AIIOS-EVENT-9002"
    retryable = False


# --- retry.py ---


def test_compute_backoff_delay_grows_exponentially_within_the_jitter_band() -> None:
    delay_1 = compute_backoff_delay(1, base_seconds=1.0, max_seconds=100.0)
    delay_3 = compute_backoff_delay(3, base_seconds=1.0, max_seconds=100.0)

    assert 1.0 <= delay_1 <= 2.0
    assert 4.0 <= delay_3 <= 5.0


def test_compute_backoff_delay_is_capped_at_max_seconds() -> None:
    delay = compute_backoff_delay(20, base_seconds=1.0, max_seconds=5.0)

    assert delay <= 5.0 + 1.0  # capped base, plus at most one base_seconds of jitter


def test_is_retryable_honors_a_framework_exceptions_own_flag() -> None:
    assert is_retryable(_RetryableFrameworkError("boom")) is True
    assert is_retryable(_FatalFrameworkError("boom")) is False


def test_is_retryable_classifies_plain_exceptions_by_type() -> None:
    assert is_retryable(ConnectionError("refused")) is True
    assert is_retryable(TimeoutError("slow")) is True
    assert is_retryable(ValueError("bad input")) is False


def test_retry_policy_delay_for_uses_its_own_bounds() -> None:
    policy = RetryPolicy(backoff_base_seconds=2.0, backoff_max_seconds=10.0)

    assert 2.0 <= policy.delay_for(1) <= 4.0


def test_retry_policy_defaults_match_the_module_constants() -> None:
    policy = RetryPolicy()

    assert policy.delay_for(100) <= DEFAULT_RETRY_BACKOFF_MAX_SECONDS + policy.backoff_base_seconds


def test_retry_policy_classify_defaults_to_is_retryable() -> None:
    policy = RetryPolicy()

    assert policy.classify(ConnectionError()) is True
    assert policy.classify(ValueError()) is False


# --- dead_letter.py (real RabbitMQ) ---


def _unique_event_name() -> str:
    return f"deadletter.test.{uuid.uuid4().hex}"


async def _publish_and_exhaust_retries(
    connection: AbstractRobustConnection, event_name: str, event_cls: type[BaseEvent]
) -> None:
    """Publish one event whose handler always fails, so it lands on the DLQ.

    Closes the consuming channel once the message has exhausted its
    retries, so the still-registered ``always_fails`` handler can't pick
    the message right back up when a later test step (e.g. replay)
    re-publishes it onto the original queue.
    """
    registry = EventRegistry()
    registry.register(event_cls)
    queue_manager = QueueManager(connection)
    publisher = EventPublisher(queue_manager)
    subscriber = EventSubscriber(queue_manager, registry=registry)

    attempts: list[int] = []

    async def always_fails(event: BaseEvent) -> None:
        attempts.append(1)
        raise ValueError("handler intentionally fails for dead-letter test")

    await subscriber.subscribe(event_name, always_fails, max_retries=1)
    await publisher.publish(event_cls(source_service="test-service"))

    for _ in range(80):
        if len(attempts) >= 2:  # original attempt + 1 retry, then dead-lettered
            await (await queue_manager.channel()).close()
            return
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"Handler only saw {len(attempts)} attempt(s); message never exhausted retries."
    )


async def test_inspect_dead_letters_peeks_without_consuming(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    name = _unique_event_name()

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    await _publish_and_exhaust_retries(rabbitmq_connection, name, _Event)
    queue_manager = QueueManager(rabbitmq_connection)

    first_peek = await inspect_dead_letters(queue_manager, name)
    second_peek = await inspect_dead_letters(queue_manager, name)

    assert len(first_peek) == 1
    assert first_peek[0].payload["event_name"] == name
    assert len(second_peek) == 1  # still there -- inspecting doesn't consume


async def test_replay_dead_letters_moves_the_message_back_to_the_original_queue(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    name = _unique_event_name()

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    await _publish_and_exhaust_retries(rabbitmq_connection, name, _Event)
    queue_manager = QueueManager(rabbitmq_connection)

    replayed_count = await replay_dead_letters(queue_manager, name)

    assert replayed_count == 1
    remaining_in_dlq = await inspect_dead_letters(queue_manager, name)
    assert remaining_in_dlq == []

    channel = await queue_manager.channel()
    original_queue = await channel.declare_queue(
        EventPublisher.queue_name_for(name), durable=True, passive=True
    )
    assert original_queue.declaration_result.message_count == 1


async def test_purge_dead_letters_permanently_removes_messages(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    name = _unique_event_name()

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    await _publish_and_exhaust_retries(rabbitmq_connection, name, _Event)
    queue_manager = QueueManager(rabbitmq_connection)

    purged_count = await purge_dead_letters(queue_manager, name)

    assert purged_count == 1
    assert await inspect_dead_letters(queue_manager, name) == []


async def test_inspect_replay_purge_dead_letters_return_immediately_for_limit_zero(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    name = _unique_event_name()

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    await _publish_and_exhaust_retries(rabbitmq_connection, name, _Event)
    queue_manager = QueueManager(rabbitmq_connection)

    assert await inspect_dead_letters(queue_manager, name, limit=0) == []
    assert await replay_dead_letters(queue_manager, name, limit=0) == 0
    assert await purge_dead_letters(queue_manager, name, limit=0) == 0

    # The message is still there -- a limit of 0 must not have consumed it.
    assert len(await inspect_dead_letters(queue_manager, name)) == 1


async def test_inspect_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await inspect_dead_letters(queue_manager, _unique_event_name())


async def test_replay_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await replay_dead_letters(queue_manager, _unique_event_name())


async def test_purge_dead_letters_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)

    with pytest.raises(DeadLetterError):
        await purge_dead_letters(queue_manager, _unique_event_name())


async def test_subscriber_sleeps_before_a_non_final_retry(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    """With max_retries > 1, a failing handler's first retry should be delayed."""
    name = _unique_event_name()

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    registry = EventRegistry()
    registry.register(_Event)
    queue_manager = QueueManager(rabbitmq_connection)
    publisher = EventPublisher(queue_manager)
    policy = RetryPolicy(backoff_base_seconds=0.2, backoff_max_seconds=0.3)
    subscriber = EventSubscriber(queue_manager, registry=registry, retry_policy=policy)

    attempt_times: list[float] = []

    async def always_fails(event: BaseEvent) -> None:
        attempt_times.append(asyncio.get_event_loop().time())
        raise ConnectionError("transient failure")

    await subscriber.subscribe(name, always_fails, max_retries=3)
    await publisher.publish(_Event(source_service="test-service"))

    for _ in range(50):
        if len(attempt_times) >= 2:
            break
        await asyncio.sleep(0.1)

    assert len(attempt_times) >= 2
    assert attempt_times[1] - attempt_times[0] >= 0.15  # the backoff sleep actually happened


async def test_publisher_retries_are_exhausted_and_raise_publish_failed_error() -> None:
    class _ExplodingQueueManager:
        async def declare_queue_with_dlq(self, queue_name: str) -> tuple[str, str]:
            raise ConnectionError("broker unreachable")

    policy = RetryPolicy(max_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    publisher = EventPublisher(_ExplodingQueueManager(), retry_policy=policy)  # type: ignore[arg-type]

    class _Event(BaseEvent):
        event_name: ClassVar[str] = "publisher.retry.test"

    with pytest.raises(EventPublishFailedError):
        await publisher.publish(_Event(source_service="test-service"))


async def test_publisher_does_not_retry_a_non_retryable_failure() -> None:
    attempts = 0

    class _ExplodingQueueManager:
        async def declare_queue_with_dlq(self, queue_name: str) -> tuple[str, str]:
            nonlocal attempts
            attempts += 1
            raise ValueError("not a transient error")

    policy = RetryPolicy(max_attempts=5, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    publisher = EventPublisher(_ExplodingQueueManager(), retry_policy=policy)  # type: ignore[arg-type]

    class _Event(BaseEvent):
        event_name: ClassVar[str] = "publisher.retry.nonretryable"

    with pytest.raises(EventPublishFailedError):
        await publisher.publish(_Event(source_service="test-service"))

    assert attempts == 1
