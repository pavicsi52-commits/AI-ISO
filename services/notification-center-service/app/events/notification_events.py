"""Domain events this service publishes (docs/055 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every notification write raises and the caller gets a 400 for a request
that did nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "notification-center-service"


@default_registry.register
class NotificationCreatedEvent(DomainEvent):
    """A notification was created."""

    event_name: ClassVar[str] = "NotificationCreated"


@default_registry.register
class NotificationQueuedEvent(DomainEvent):
    """A notification's delivery over one channel was queued."""

    event_name: ClassVar[str] = "NotificationQueued"


@default_registry.register
class NotificationSentEvent(DomainEvent):
    """A notification was handed off to its channel successfully."""

    event_name: ClassVar[str] = "NotificationSent"


@default_registry.register
class NotificationDeliveredEvent(DomainEvent):
    """A channel confirmed delivery."""

    event_name: ClassVar[str] = "NotificationDelivered"


@default_registry.register
class NotificationReadEvent(DomainEvent):
    """A recipient read a notification."""

    event_name: ClassVar[str] = "NotificationRead"


@default_registry.register
class NotificationAcknowledgedEvent(DomainEvent):
    """A recipient acknowledged a notification."""

    event_name: ClassVar[str] = "NotificationAcknowledged"


@default_registry.register
class NotificationFailedEvent(DomainEvent):
    """A notification's delivery exhausted its retries and was dead-lettered."""

    event_name: ClassVar[str] = "NotificationFailed"


@default_registry.register
class NotificationRetriedEvent(DomainEvent):
    """A failed delivery was attempted again."""

    event_name: ClassVar[str] = "NotificationRetried"


@default_registry.register
class AnnouncementPublishedEvent(DomainEvent):
    """An announcement was published to its audience."""

    event_name: ClassVar[str] = "AnnouncementPublished"


__all__ = [
    "SOURCE_SERVICE",
    "AnnouncementPublishedEvent",
    "NotificationAcknowledgedEvent",
    "NotificationCreatedEvent",
    "NotificationDeliveredEvent",
    "NotificationFailedEvent",
    "NotificationQueuedEvent",
    "NotificationReadEvent",
    "NotificationRetriedEvent",
    "NotificationSentEvent",
]
