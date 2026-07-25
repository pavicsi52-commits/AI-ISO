"""Tests for connection management and retry-policy classification/backoff."""

from __future__ import annotations

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.exceptions.event import EventError
from shared_core.queue.connection import (
    create_connection,
    create_connection_pool,
    create_connection_with_retry,
    graceful_shutdown,
    wait_for_broker,
)
from shared_core.queue.exceptions import ConnectionFailedError
from shared_core.queue.retry import (
    RetryPolicy,
    compute_backoff_delay,
    compute_backoff_delay_ms,
    is_retryable,
)

from tests.unit.conftest import rabbitmq_test_settings


class _RetryableFrameworkError(EventError):
    error_code = "AIIOS-QUEUE-9001"
    retryable = True


class _FatalFrameworkError(EventError):
    error_code = "AIIOS-QUEUE-9002"
    retryable = False


# --- retry.py ---


def test_compute_backoff_delay_grows_exponentially_within_the_jitter_band() -> None:
    delay_1 = compute_backoff_delay(1, base_seconds=1.0, max_seconds=100.0)
    delay_3 = compute_backoff_delay(3, base_seconds=1.0, max_seconds=100.0)

    assert 1.0 <= delay_1 <= 2.0
    assert 4.0 <= delay_3 <= 5.0


def test_compute_backoff_delay_is_capped_at_max_seconds() -> None:
    delay = compute_backoff_delay(20, base_seconds=1.0, max_seconds=5.0)

    assert delay <= 6.0


def test_compute_backoff_delay_ms_has_no_jitter_and_rounds_to_whole_seconds() -> None:
    assert compute_backoff_delay_ms(1, base_seconds=1.0, max_seconds=60.0, multiplier=2.0) == 1000
    assert compute_backoff_delay_ms(2, base_seconds=1.0, max_seconds=60.0, multiplier=2.0) == 2000
    assert compute_backoff_delay_ms(3, base_seconds=1.0, max_seconds=60.0, multiplier=2.0) == 4000


def test_compute_backoff_delay_ms_is_capped_at_max_seconds() -> None:
    delay_ms = compute_backoff_delay_ms(20, base_seconds=1.0, max_seconds=10.0, multiplier=2.0)

    assert delay_ms == 10_000


def test_is_retryable_defaults_to_permissive_for_plain_exceptions() -> None:
    """Consumer handlers are arbitrary business logic -- retry unless told not to."""
    assert is_retryable(RuntimeError("boom")) is True
    assert is_retryable(ValueError("bad input")) is True
    assert is_retryable(ConnectionError("refused")) is True


def test_is_retryable_honors_a_framework_exceptions_own_flag() -> None:
    assert is_retryable(_RetryableFrameworkError("boom")) is True
    assert is_retryable(_FatalFrameworkError("boom")) is False


def test_retry_policy_delay_for_uses_its_own_bounds() -> None:
    policy = RetryPolicy(backoff_base_seconds=2.0, backoff_max_seconds=10.0)

    assert 2.0 <= policy.delay_for(1) <= 4.0


def test_retry_policy_classify_defaults_to_is_retryable() -> None:
    policy = RetryPolicy()

    assert policy.classify(RuntimeError()) is True
    assert policy.classify(_FatalFrameworkError("boom")) is False


# --- connection.py (real RabbitMQ) ---


async def test_create_connection_connects_to_the_real_broker() -> None:
    connection = await create_connection(rabbitmq_test_settings())
    try:
        assert connection.is_closed is False
    finally:
        await connection.close()


async def test_create_connection_with_retry_succeeds_on_a_reachable_broker() -> None:
    connection = await create_connection_with_retry(rabbitmq_test_settings(), max_attempts=2)
    try:
        assert connection.is_closed is False
    finally:
        await connection.close()


async def test_create_connection_with_retry_raises_after_exhausting_attempts() -> None:
    unreachable = rabbitmq_test_settings()
    unreachable.rabbitmq_port = 1  # nothing listens here

    with pytest.raises(ConnectionFailedError):
        await create_connection_with_retry(
            unreachable, max_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.02
        )


async def test_wait_for_broker_returns_once_the_connection_is_ready(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    await wait_for_broker(rabbitmq_connection, timeout_seconds=5.0)  # must not raise


async def test_wait_for_broker_raises_on_an_already_closed_connection() -> None:
    connection = await create_connection(rabbitmq_test_settings())
    await connection.close()

    with pytest.raises(ConnectionFailedError):
        await wait_for_broker(connection, timeout_seconds=1.0)


async def test_graceful_shutdown_closes_an_open_connection() -> None:
    connection = await create_connection(rabbitmq_test_settings())

    await graceful_shutdown(connection)

    assert connection.is_closed is True


async def test_graceful_shutdown_on_an_already_closed_connection_is_a_no_op() -> None:
    connection = await create_connection(rabbitmq_test_settings())
    await connection.close()

    await graceful_shutdown(connection)  # must not raise

    assert connection.is_closed is True


async def test_create_connection_pool_acquires_a_real_connection() -> None:
    pool = create_connection_pool(rabbitmq_test_settings(), pool_size=2)
    try:
        async with pool.acquire() as connection:
            assert connection.is_closed is False
    finally:
        await pool.close()
