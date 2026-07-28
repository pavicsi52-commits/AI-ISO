"""Alerting service domain events.

Per docs/045 "EVENTS": AlertCreated, AlertAcknowledged, AlertEscalated,
AlertSuppressed, AlertResolved, AlertClosed, AlertExpired,
AlertNotificationSent. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`, registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class AlertCreatedEvent(DomainEvent):
    """A new alert was raised."""

    event_name: ClassVar[str] = "AlertCreated"


@default_registry.register
class AlertAcknowledgedEvent(DomainEvent):
    """An alert was acknowledged."""

    event_name: ClassVar[str] = "AlertAcknowledged"


@default_registry.register
class AlertEscalatedEvent(DomainEvent):
    """An alert was escalated to a further level."""

    event_name: ClassVar[str] = "AlertEscalated"


@default_registry.register
class AlertSuppressedEvent(DomainEvent):
    """An alert was suppressed rather than raised for attention."""

    event_name: ClassVar[str] = "AlertSuppressed"


@default_registry.register
class AlertResolvedEvent(DomainEvent):
    """An alert was resolved."""

    event_name: ClassVar[str] = "AlertResolved"


@default_registry.register
class AlertClosedEvent(DomainEvent):
    """An alert was closed."""

    event_name: ClassVar[str] = "AlertClosed"


@default_registry.register
class AlertExpiredEvent(DomainEvent):
    """An alert expired without being resolved."""

    event_name: ClassVar[str] = "AlertExpired"


@default_registry.register
class AlertNotificationSentEvent(DomainEvent):
    """A notification for an alert was delivered."""

    event_name: ClassVar[str] = "AlertNotificationSent"


__all__ = [
    "AlertAcknowledgedEvent",
    "AlertClosedEvent",
    "AlertCreatedEvent",
    "AlertEscalatedEvent",
    "AlertExpiredEvent",
    "AlertNotificationSentEvent",
    "AlertResolvedEvent",
    "AlertSuppressedEvent",
]
