"""Event Framework factory.

Assembles the registry, publisher, subscriber, bus, and manager into one
object a service builds exactly once at startup -- mirroring
:func:`shared_core.cache.factory.create_cache_framework` (Prompt 019) and
:func:`shared_core.database.factory` (Prompt 018).
"""

from __future__ import annotations

from dataclasses import dataclass

from aio_pika.abc import AbstractRobustConnection

from shared_core.config.settings import RabbitMQSettings
from shared_core.events.bus import EventBus
from shared_core.events.manager import EventManager
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.retry import RetryPolicy
from shared_core.events.subscriber import EventSubscriber
from shared_core.queue.connection import create_connection
from shared_core.queue.manager import QueueManager


@dataclass(slots=True)
class EventFramework:
    """Everything a service needs to publish/subscribe to events, assembled once at startup."""

    connection: AbstractRobustConnection
    queue_manager: QueueManager
    manager: EventManager

    async def shutdown(self) -> None:
        """Close the underlying RabbitMQ connection. Call once at service shutdown."""
        await self.connection.close()


async def create_event_framework(
    settings: RabbitMQSettings,
    *,
    registry: EventRegistry = default_registry,
    retry_policy: RetryPolicy | None = None,
) -> EventFramework:
    """Build an :class:`EventFramework` from Configuration Framework settings (Prompt 013)."""
    connection = await create_connection(settings)
    queue_manager = QueueManager(connection)
    policy = retry_policy or RetryPolicy()
    publisher = EventPublisher(queue_manager, retry_policy=policy)
    subscriber = EventSubscriber(queue_manager, registry=registry, retry_policy=policy)
    bus = EventBus(publisher, subscriber, registry=registry)
    manager = EventManager(bus, registry=registry)
    return EventFramework(connection=connection, queue_manager=queue_manager, manager=manager)


__all__ = ["EventFramework", "create_event_framework"]
