"""Dead letter handling.

Per docs/020_Enterprise_Event_Framework.md.txt "DEAD LETTER": Move failed
events, Store metadata, Allow replay, Allow inspection. Moving a failed
event to its dead-letter queue is already automatic --
:meth:`shared_core.queue.manager.QueueManager.declare_queue_with_dlq`
(Prompt 012) wires every event queue to one. This module is what acts on
what's already there: peek at it, replay it back onto the original queue,
or purge it -- reusing that same queue's dead-letter naming convention
rather than a parallel storage mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared_core.events.constants import (
    DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS,
    DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
)
from shared_core.events.exceptions import DeadLetterError
from shared_core.events.publisher import EventPublisher
from shared_core.helpers.json_helper import from_json
from shared_core.queue.manager import QueueManager


@dataclass(frozen=True, slots=True)
class DeadLetteredEvent:
    """One message sitting in an event's dead-letter queue."""

    payload: dict[str, Any]
    redelivered: bool


def dead_letter_queue_name_for(event_name: str) -> str:
    """Return the dead-letter queue name for *event_name*'s event queue."""
    return f"{EventPublisher.queue_name_for(event_name)}.dlq"


async def inspect_dead_letters(
    queue_manager: QueueManager,
    event_name: str,
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
) -> list[DeadLetteredEvent]:
    """Peek at up to *limit* dead-lettered messages for *event_name*, without consuming them.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        queue = await channel.get_queue(dead_letter_queue_name_for(event_name))
        # Fetch every message first, without acking/nacking as we go: nacking
        # a message immediately requeues it at the head of the queue, which
        # would put it right back in front of the next `get()` call and
        # fetch the same message over and over instead of walking the queue.
        fetched = []
        for _ in range(limit):
            message = await queue.get(
                no_ack=False, fail=False, timeout=DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS
            )
            if message is None:
                break
            fetched.append(message)

        found = [
            DeadLetteredEvent(
                payload=from_json(message.body), redelivered=bool(message.redelivered)
            )
            for message in fetched
        ]
        for message in fetched:
            await message.nack(requeue=True)
        return found
    except Exception as exc:
        raise DeadLetterError(f"Failed to inspect dead letters for '{event_name}'.") from exc


async def replay_dead_letters(
    queue_manager: QueueManager,
    event_name: str,
    *,
    limit: int = DEFAULT_DEAD_LETTER_INSPECT_LIMIT,
) -> int:
    """Re-publish up to *limit* dead-lettered messages back onto *event_name*'s original queue.

    Returns the count actually replayed.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        queue = await channel.get_queue(dead_letter_queue_name_for(event_name))
        original_queue_name = EventPublisher.queue_name_for(event_name)
        replayed = 0
        for _ in range(limit):
            message = await queue.get(
                no_ack=False, fail=False, timeout=DEFAULT_DEAD_LETTER_GET_TIMEOUT_SECONDS
            )
            if message is None:
                break
            payload = from_json(message.body)
            await queue_manager.publish(original_queue_name, payload)
            await message.ack()
            replayed += 1
        return replayed
    except Exception as exc:
        raise DeadLetterError(f"Failed to replay dead letters for '{event_name}'.") from exc


async def purge_dead_letters(
    queue_manager: QueueManager,
    event_name: str,
    *,
    limit: int | None = None,
) -> int:
    """Permanently delete dead-lettered messages for *event_name* (up to *limit*, or all of them).

    Returns the count purged.

    Raises:
        DeadLetterError: If the dead-letter queue can't be read.
    """
    try:
        channel = await queue_manager.channel()
        queue = await channel.get_queue(dead_letter_queue_name_for(event_name))
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
        raise DeadLetterError(f"Failed to purge dead letters for '{event_name}'.") from exc


__all__ = [
    "DeadLetteredEvent",
    "dead_letter_queue_name_for",
    "inspect_dead_letters",
    "purge_dead_letters",
    "replay_dead_letters",
]
