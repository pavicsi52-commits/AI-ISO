"""Delayed jobs.

Per docs/021_Enterprise_Queue_Framework.md.txt "DELAYED JOBS": Execute
After Time, Specific Date (both here); Cron, Recurring (built on top of
this in :mod:`shared_core.queue.scheduler`).

RabbitMQ has no native per-message delay without the
``rabbitmq-delayed-message-exchange`` community plugin, which this
project's ``rabbitmq:3-management-alpine`` image doesn't ship.
Implemented instead with the standard TTL + dead-letter pattern: publish
the message to a queue-level-TTL "holding" queue dedicated to that exact
delay duration (never consumed directly); once a message's TTL expires,
RabbitMQ dead-letters it straight back onto the real queue. One holding
queue per distinct delay duration keeps every message in it sharing the
same TTL, avoiding the well-known "head-of-queue" expiry-ordering quirk
classic queues have when messages in the same queue carry different TTLs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aio_pika.abc import AbstractChannel

from shared_core.queue.constants import MAX_DELAY_MILLISECONDS, MIN_DELAY_MILLISECONDS
from shared_core.queue.exceptions import InvalidDelayError


def delay_queue_name_for(queue_name: str, delay_ms: int) -> str:
    """Return the holding-queue name for *queue_name* at *delay_ms*."""
    return f"{queue_name}.delay.{delay_ms}"


def validate_delay(delay_ms: int) -> None:
    """Ensure *delay_ms* is within the framework's supported range.

    Raises:
        InvalidDelayError: If *delay_ms* is negative or exceeds the
            maximum supported delay.
    """
    if not MIN_DELAY_MILLISECONDS <= delay_ms <= MAX_DELAY_MILLISECONDS:
        raise InvalidDelayError(
            f"Delay must be between {MIN_DELAY_MILLISECONDS} and "
            f"{MAX_DELAY_MILLISECONDS} milliseconds, got {delay_ms}."
        )


def delay_until(target: datetime, *, now: datetime | None = None) -> int:
    """Compute the millisecond delay from *now* until *target* ("Specific Date").

    Raises:
        InvalidDelayError: If *target* is in the past, or too far in the future.
    """
    reference = now or datetime.now(UTC)
    delay_ms = int((target - reference).total_seconds() * 1000)
    validate_delay(delay_ms)
    return delay_ms


async def declare_delay_queue(channel: AbstractChannel, queue_name: str, delay_ms: int) -> str:
    """Declare (if needed) the holding queue for *queue_name* at *delay_ms*.

    Returns:
        The holding queue's name.
    """
    validate_delay(delay_ms)
    holding_name = delay_queue_name_for(queue_name, delay_ms)
    await channel.declare_queue(
        holding_name,
        durable=True,
        arguments={
            "x-message-ttl": delay_ms,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": queue_name,
        },
    )
    return holding_name


__all__ = ["declare_delay_queue", "delay_queue_name_for", "delay_until", "validate_delay"]
