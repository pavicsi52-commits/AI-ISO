"""Enterprise Queue Framework factory.

Assembles the connection, manager, producer, consumer, and scheduler
into one object a service builds exactly once at startup -- mirroring
:func:`shared_core.events.factory.create_event_framework` (Prompt 020)
and :func:`shared_core.cache.factory.create_cache_framework` (Prompt 019).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aio_pika.abc import AbstractRobustConnection

from shared_core.config.settings import RabbitMQSettings
from shared_core.queue.connection import create_connection_with_retry, graceful_shutdown
from shared_core.queue.consumer import Consumer
from shared_core.queue.manager import QueueManager
from shared_core.queue.producer import Producer
from shared_core.queue.retry import RetryPolicy
from shared_core.queue.scheduler import TaskScheduler


@dataclass(slots=True)
class QueueFramework:
    """Everything a service needs to produce/consume queue messages, assembled once at startup."""

    connection: AbstractRobustConnection
    manager: QueueManager
    producer: Producer
    consumer: Consumer
    scheduler: TaskScheduler = field(default_factory=TaskScheduler)

    async def shutdown(self) -> None:
        """Close the underlying broker connection. Call once at service shutdown."""
        await graceful_shutdown(self.connection)


async def create_queue_framework(
    settings: RabbitMQSettings, *, retry_policy: RetryPolicy | None = None
) -> QueueFramework:
    """Build a :class:`QueueFramework` from Configuration Framework settings (Prompt 013).

    Connects with retry ("Connection Management") rather than a single
    bare attempt, since this is meant for service startup, where the
    broker (a separate container/process) may not be accepting
    connections yet.
    """
    connection = await create_connection_with_retry(settings)
    manager = QueueManager(connection)
    policy = retry_policy or RetryPolicy()
    producer = Producer(manager, retry_policy=policy)
    consumer = Consumer(manager, retry_policy=policy)
    return QueueFramework(
        connection=connection, manager=manager, producer=producer, consumer=consumer
    )


__all__ = ["QueueFramework", "create_queue_framework"]
