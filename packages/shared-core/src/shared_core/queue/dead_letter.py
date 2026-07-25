"""Dead letter handling.

Per docs/021_Enterprise_Queue_Framework.md.txt "DEAD LETTER": "Store
failed jobs." Support Replay, Inspection, Filtering, Export, Purge.
Moving a failed message to its dead-letter queue is already automatic --
:meth:`shared_core.queue.manager.QueueManager.declare_queue_with_dlq`
wires every queue to one. This module is what acts on what's already
there.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from shared_core.queue.constants import (
    DEAD_LETTER_QUEUE_SUFFIX,
    DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS,
    DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
)
from shared_core.queue.exceptions import DeadLetterError
from shared_core.queue.serializer import SerializationFormat, deserialize_message

if TYPE_CHECKING:
    from shared_core.queue.manager import QueueManager


@dataclass(frozen=True, slots=True)
class DeadLetteredMessage:
    """One message sitting in a dead-letter queue."""

    payload: dict[str, Any]
    redelivered: bool


def dead_letter_queue_name_for(queue_name: str) -> str:
    """Return the dead-letter queue name for *queue_name*."""
    return f"{queue_name}{DEAD_LETTER_QUEUE_SUFFIX}"


async def _fetch_all(
    channel: AbstractChannel, dlq_name: str, limit: int
) -> list[AbstractIncomingMessage]:
    """Fetch up to *limit* messages from *dlq_name*, without acking/nacking as we go.

    Nacking a message immediately requeues it at the head of the queue --
    interleaving nack with fetch would put it right back in front of the
    next ``get()`` call and re-fetch the same message repeatedly instead
    of walking the queue.
    """
    queue = await channel.get_queue(dlq_name)
    fetched: list[AbstractIncomingMessage] = []
    for _ in range(limit):
        message = await queue.get(
            no_ack=False, fail=False, timeout=DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS
        )
        if message is None:
            break
        fetched.append(message)
    return fetched


async def inspect_dead_letters(
    queue_manager: QueueManager,
    queue_name: str,
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
    format: SerializationFormat = SerializationFormat.JSON,
) -> list[DeadLetteredMessage]:
    """Peek at up to *limit* dead-lettered messages for *queue_name*, without consuming them.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        fetched = await _fetch_all(channel, dead_letter_queue_name_for(queue_name), limit)
        found = [
            DeadLetteredMessage(
                payload=deserialize_message(message.body, format=format),
                redelivered=bool(message.redelivered),
            )
            for message in fetched
        ]
        for message in fetched:
            await message.nack(requeue=True)
        return found
    except Exception as exc:
        raise DeadLetterError(f"Failed to inspect dead letters for '{queue_name}'.") from exc


async def filter_dead_letters(
    queue_manager: QueueManager,
    queue_name: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
    format: SerializationFormat = SerializationFormat.JSON,
) -> list[DeadLetteredMessage]:
    """Return only the dead-lettered messages for *queue_name* whose payload matches *predicate*.

    Non-consuming, same as :func:`inspect_dead_letters` (which this is
    built on).
    """
    messages = await inspect_dead_letters(queue_manager, queue_name, limit=limit, format=format)
    return [message for message in messages if predicate(message.payload)]


async def export_dead_letters(
    queue_manager: QueueManager,
    queue_name: str,
    destination: Path,
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
    format: SerializationFormat = SerializationFormat.JSON,
) -> int:
    """Write every dead-lettered message for *queue_name* to *destination* as a JSON array.

    Returns:
        The number of messages exported. Non-consuming.
    """
    messages = await inspect_dead_letters(queue_manager, queue_name, limit=limit, format=format)
    content = json.dumps([message.payload for message in messages], default=str, indent=2)
    await asyncio.to_thread(destination.write_text, content, encoding="utf-8")
    return len(messages)


async def replay_dead_letters(
    queue_manager: QueueManager,
    queue_name: str,
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
    format: SerializationFormat = SerializationFormat.JSON,
) -> int:
    """Re-publish up to *limit* dead-lettered messages back onto *queue_name*.

    Returns:
        The count actually replayed.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        fetched = await _fetch_all(channel, dead_letter_queue_name_for(queue_name), limit)
        replayed = 0
        for message in fetched:
            payload = deserialize_message(message.body, format=format)
            await queue_manager.publish(queue_name, payload)
            await message.ack()
            replayed += 1
        return replayed
    except Exception as exc:
        raise DeadLetterError(f"Failed to replay dead letters for '{queue_name}'.") from exc


async def purge_dead_letters(
    queue_manager: QueueManager,
    queue_name: str,
    *,
    limit: int | None = None,
) -> int:
    """Permanently delete dead-lettered messages for *queue_name* (up to *limit*, or all).

    Returns:
        The count purged.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        queue = await channel.get_queue(dead_letter_queue_name_for(queue_name))
        purged = 0
        while limit is None or purged < limit:
            message = await queue.get(
                no_ack=False, fail=False, timeout=DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS
            )
            if message is None:
                break
            await message.ack()
            purged += 1
        return purged
    except Exception as exc:
        raise DeadLetterError(f"Failed to purge dead letters for '{queue_name}'.") from exc


__all__ = [
    "DeadLetteredMessage",
    "dead_letter_queue_name_for",
    "export_dead_letters",
    "filter_dead_letters",
    "inspect_dead_letters",
    "purge_dead_letters",
    "replay_dead_letters",
]
