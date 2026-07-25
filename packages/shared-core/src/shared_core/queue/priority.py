"""Priority queues.

Per docs/021_Enterprise_Queue_Framework.md.txt "PRIORITY": Critical,
High, Normal, Low, Background.
"""

from __future__ import annotations

from typing import Any

from aio_pika.abc import AbstractChannel, AbstractQueue

from shared_core.enums.priority import Priority
from shared_core.queue.constants import PRIORITY_LEVELS, PRIORITY_QUEUE_MAX_PRIORITY
from shared_core.queue.exceptions import InvalidPriorityError


def priority_level(priority: Priority) -> int:
    """Return the numeric RabbitMQ priority level (0-9, higher runs first) for *priority*.

    Raises:
        InvalidPriorityError: If *priority* isn't one of the framework's
            five supported levels (defensive -- ``Priority`` is a
            ``StrEnum``, so this should be unreachable for any value
            actually constructed through it).
    """
    try:
        return PRIORITY_LEVELS[priority]
    except KeyError as exc:
        raise InvalidPriorityError(f"Unsupported priority level: {priority!r}.") from exc


async def declare_priority_queue(
    channel: AbstractChannel,
    queue_name: str,
    *,
    durable: bool = True,
    max_priority: int = PRIORITY_QUEUE_MAX_PRIORITY,
    arguments: dict[str, Any] | None = None,
) -> AbstractQueue:
    """Declare a queue that honors per-message ``priority`` ("Priority Queue" queue type)."""
    merged_arguments: dict[str, Any] = {"x-max-priority": max_priority, **(arguments or {})}
    return await channel.declare_queue(queue_name, durable=durable, arguments=merged_arguments)


__all__ = ["declare_priority_queue", "priority_level"]
