"""Event subscriber.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT CONSUMER" (renamed
Subscriber here to match this framework's own file naming): Consume
Events, Handler Registration, Concurrent Consumption, Error Handling,
Acknowledgement.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.events.base import BaseEvent
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.retry import RetryPolicy
from shared_core.events.serializer import deserialize_event
from shared_core.events.versioning import VersionMigrator
from shared_core.queue.manager import QueueManager
from shared_core.types.queue import QueueMessage

EventHandlerFn = Callable[[BaseEvent], Awaitable[None]]


class EventSubscriber:
    """Consumes events of a given name and dispatches them to a handler.

    Backoff between retries ("Error Handling") is layered on top of
    :meth:`shared_core.queue.manager.QueueManager.consume`'s own
    count-based retry/dead-letter mechanism: this class sleeps before
    re-raising a handler's exception when another attempt will happen,
    but the queue manager still owns the actual requeue/dead-letter/ack
    decision ("Acknowledgement"), unchanged. Attempt numbers are tracked
    in-memory, keyed by the event's own stable ``event_id`` (unchanged
    across RabbitMQ redeliveries of the same message), since the queue
    manager doesn't expose its internal retry count to handlers.
    """

    def __init__(
        self,
        queue_manager: QueueManager,
        *,
        registry: EventRegistry = default_registry,
        retry_policy: RetryPolicy | None = None,
        migrator: VersionMigrator | None = None,
    ) -> None:
        self._queue_manager = queue_manager
        self._registry = registry
        self._retry_policy = retry_policy or RetryPolicy()
        self._migrator = migrator
        self._attempt_counts: dict[UUID, int] = {}

    async def subscribe(
        self,
        event_name: str,
        handler: EventHandlerFn,
        *,
        max_retries: int | None = None,
    ) -> None:
        """Subscribe *handler* to every event published under *event_name* ("Handler Registration").

        Each call to ``subscribe`` starts one logical consumer; RabbitMQ
        itself fans deliveries out across however many processes/tasks
        call it for the same queue ("Concurrent Consumption").
        """
        queue_name = EventPublisher.queue_name_for(event_name)
        await self._queue_manager.declare_queue_with_dlq(queue_name)
        effective_max_retries = (
            max_retries if max_retries is not None else self._retry_policy.max_attempts
        )

        async def _dispatch(message: QueueMessage) -> None:
            await self._handle(message, handler, effective_max_retries)

        await self._queue_manager.consume(queue_name, _dispatch, max_retries=effective_max_retries)

    async def _handle(
        self, message: QueueMessage, handler: EventHandlerFn, max_retries: int
    ) -> None:
        event: BaseEvent = deserialize_event(
            message, registry=self._registry, migrator=self._migrator
        )
        try:
            await handler(event)
        except Exception as exc:
            attempt = self._attempt_counts.get(event.event_id, 0) + 1
            self._attempt_counts[event.event_id] = attempt
            will_retry = attempt < max_retries and self._retry_policy.classify(exc)
            if will_retry:
                await asyncio.sleep(self._retry_policy.delay_for(attempt))
            else:
                self._attempt_counts.pop(event.event_id, None)
            raise
        else:
            self._attempt_counts.pop(event.event_id, None)


__all__ = ["EventHandlerFn", "EventSubscriber"]
