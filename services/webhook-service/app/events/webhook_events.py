"""Domain events this service publishes (docs/057 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every delivery/replay call raises and the caller gets a 400 for a
request that did nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "webhook-service"


@default_registry.register
class WebhookReceivedEvent(DomainEvent):
    """An incoming webhook (or internal event) was received."""

    event_name: ClassVar[str] = "WebhookReceived"


@default_registry.register
class WebhookValidatedEvent(DomainEvent):
    """An incoming webhook passed signature/schema validation."""

    event_name: ClassVar[str] = "WebhookValidated"


@default_registry.register
class WebhookDeliveredEvent(DomainEvent):
    """An outgoing delivery succeeded."""

    event_name: ClassVar[str] = "WebhookDelivered"


@default_registry.register
class WebhookFailedEvent(DomainEvent):
    """An outgoing delivery attempt failed."""

    event_name: ClassVar[str] = "WebhookFailed"


@default_registry.register
class WebhookRetriedEvent(DomainEvent):
    """A failed delivery was queued for another attempt."""

    event_name: ClassVar[str] = "WebhookRetried"


@default_registry.register
class WebhookReplayedEvent(DomainEvent):
    """A replay job redelivered a past event."""

    event_name: ClassVar[str] = "WebhookReplayed"


@default_registry.register
class EndpointRegisteredEvent(DomainEvent):
    """A new outgoing-delivery endpoint was registered."""

    event_name: ClassVar[str] = "EndpointRegistered"


@default_registry.register
class SubscriptionCreatedEvent(DomainEvent):
    """A new subscription was created."""

    event_name: ClassVar[str] = "SubscriptionCreated"


__all__ = [
    "SOURCE_SERVICE",
    "EndpointRegisteredEvent",
    "SubscriptionCreatedEvent",
    "WebhookDeliveredEvent",
    "WebhookFailedEvent",
    "WebhookReceivedEvent",
    "WebhookReplayedEvent",
    "WebhookRetriedEvent",
    "WebhookValidatedEvent",
]
