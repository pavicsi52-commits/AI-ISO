"""Event bus.

Structurally enforces docs/020_Enterprise_Event_Framework.md.txt "INTERNAL
EVENTS... Never leave the owning service": routes
:class:`~shared_core.events.base.InternalEvent` (and any other event
registered with :attr:`~shared_core.events.base.EventType.INTERNAL`)
through the in-process :class:`~shared_core.events.dispatcher.EventDispatcher`
only. Every other event type goes through the queue-backed
:class:`~shared_core.events.publisher.EventPublisher` /
:class:`~shared_core.events.subscriber.EventSubscriber`, so there is no
code path by which an internal event could reach RabbitMQ.
"""

from __future__ import annotations

from shared_core.events.base import BaseEvent, EventType
from shared_core.events.constants import DEFAULT_HANDLER_PRIORITY
from shared_core.events.dispatcher import EventDispatcher, EventFilter, EventHandler
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.subscriber import EventSubscriber


class EventBus:
    """Single entry point for publish/subscribe, routing by the event's own ``event_type``."""

    def __init__(
        self,
        publisher: EventPublisher,
        subscriber: EventSubscriber,
        *,
        dispatcher: EventDispatcher | None = None,
        registry: EventRegistry = default_registry,
    ) -> None:
        self._publisher = publisher
        self._subscriber = subscriber
        self._dispatcher = dispatcher or EventDispatcher()
        self._registry = registry

    @property
    def dispatcher(self) -> EventDispatcher:
        """The in-process dispatcher internal events are routed through."""
        return self._dispatcher

    async def publish(self, event: BaseEvent) -> None:
        """Publish *event*: in-process only if it's an internal event, over the queue otherwise."""
        if event.event_type is EventType.INTERNAL:
            await self._dispatcher.dispatch(event)
        else:
            await self._publisher.publish(event)

    async def subscribe(
        self,
        event_name: str,
        handler: EventHandler,
        *,
        priority: int = DEFAULT_HANDLER_PRIORITY,
        filter: EventFilter | None = None,
    ) -> None:
        """Subscribe *handler* to every event published under *event_name*.

        Routed the same way publishing is: internal events register
        in-process with the dispatcher; everything else subscribes
        through the queue.
        """
        event_cls = self._registry.lookup(event_name)
        if event_cls.event_type is EventType.INTERNAL:
            self._dispatcher.register(event_name, handler, priority=priority, filter=filter)
        else:
            await self._subscriber.subscribe(event_name, handler)


__all__ = ["EventBus"]
