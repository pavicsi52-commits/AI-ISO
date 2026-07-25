"""Event publisher.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT PUBLISHER":
Synchronous Publish, Asynchronous Publish, Batch Publish, Publish
Confirmation, Publish Retry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from shared_core.events.base import BaseEvent
from shared_core.events.exceptions import EventPublishFailedError
from shared_core.events.retry import RetryPolicy
from shared_core.events.serializer import serialize_event
from shared_core.queue.manager import QueueManager


class EventPublisher:
    """Publishes events onto their event-name-derived queue.

    Every event of a given name is routed to a queue called
    ``events.<event_name>``, so consumers subscribe per event type.
    Publish failures are retried under *retry_policy* ("Publish Retry")
    before raising :class:`~shared_core.events.exceptions.EventPublishFailedError`.
    """

    def __init__(
        self, queue_manager: QueueManager, *, retry_policy: RetryPolicy | None = None
    ) -> None:
        self._queue_manager = queue_manager
        self._retry_policy = retry_policy or RetryPolicy()

    @staticmethod
    def queue_name_for(event_name: str) -> str:
        """Return the queue name events of ``event_name`` are published to."""
        return f"events.{event_name}"

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event, retrying transient failures with backoff ("Synchronous Publish").

        Confirmation is implicit: :meth:`~shared_core.queue.manager.QueueManager.publish`
        (via aio-pika's persistent delivery mode) doesn't return until the
        broker has accepted the message, satisfying "Publish Confirmation"
        without a separate acknowledgement round trip.

        Raises:
            EventPublishFailedError: If every retry attempt is exhausted.
        """
        queue_name = self.queue_name_for(event.event_name)
        last_error: Exception | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                await self._queue_manager.declare_queue_with_dlq(queue_name)
                await self._queue_manager.publish(queue_name, serialize_event(event))
                return
            except Exception as exc:
                last_error = exc
                is_final_attempt = attempt == self._retry_policy.max_attempts
                if not self._retry_policy.classify(exc) or is_final_attempt:
                    break
                await asyncio.sleep(self._retry_policy.delay_for(attempt))
        raise EventPublishFailedError(
            f"Failed to publish event '{event.event_name}' after "
            f"{self._retry_policy.max_attempts} attempt(s)."
        ) from last_error

    async def publish_batch(self, events: Iterable[BaseEvent]) -> None:
        """Publish every event in *events*, in order ("Batch Publish").

        Raises:
            EventPublishFailedError: On the first event that fails all its
                retry attempts; earlier events in the batch have already
                been published and are not rolled back.
        """
        for event in events:
            await self.publish(event)

    def publish_async(self, event: BaseEvent) -> asyncio.Task[None]:
        """Schedule *event* to be published without waiting for it ("Asynchronous Publish").

        Returns the created task so callers who do want to observe
        completion/errors may ``await`` it themselves.
        """
        return asyncio.create_task(self.publish(event))


__all__ = ["EventPublisher"]
