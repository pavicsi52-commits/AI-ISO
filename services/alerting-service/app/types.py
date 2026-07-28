"""Shared type aliases for this service.

``EventPublisher`` lives here rather than in whichever service module
happened to need it first, because several of them do (ingestion,
escalation dispatch, notification delivery). Prior AI-IOS services
each defined their own copy inside one orchestrator module and
re-imported it from there, which made an arbitrary module the owner of
a type unrelated to its own responsibility.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.events.base import DomainEvent

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
"""Publishes one domain event. Satisfied by
``shared_core.events.manager.EventManager.publish``.
"""

__all__ = ["EventPublisher"]
