"""Shared type aliases for this service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.events.base import DomainEvent

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
"""Publishes one domain event.

Satisfied by ``shared_core.events.manager.EventManager.publish``.
"""

__all__ = ["EventPublisher"]
