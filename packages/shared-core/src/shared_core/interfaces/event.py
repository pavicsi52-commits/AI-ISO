"""Event publisher/consumer interfaces.

Concrete implementations live in ``shared_core.events``
(docs/020_Enterprise_Event_Framework.md.txt).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared_core.types.event import EventPayload


@runtime_checkable
class EventPublisherProtocol(Protocol):
    """Structural interface for publishing domain/integration events."""

    async def publish(self, event_name: str, payload: EventPayload) -> None:
        """Publish an event under the given name."""
        ...


@runtime_checkable
class EventConsumerProtocol(Protocol):
    """Structural interface for consuming events."""

    async def consume(self, event_name: str) -> None:
        """Begin consuming events registered under the given name."""
        ...
