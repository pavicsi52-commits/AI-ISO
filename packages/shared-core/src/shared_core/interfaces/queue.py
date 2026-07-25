"""Queue interface.

Concrete implementation is the RabbitMQ wrapper in ``shared_core.queue``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared_core.types.queue import QueueMessage


@runtime_checkable
class QueueProtocol(Protocol):
    """Structural interface for a message queue."""

    async def enqueue(self, queue_name: str, message: QueueMessage) -> None:
        """Place a message on the given queue."""
        ...

    async def dequeue(self, queue_name: str) -> QueueMessage | None:
        """Remove and return the next message from the given queue, if any."""
        ...
