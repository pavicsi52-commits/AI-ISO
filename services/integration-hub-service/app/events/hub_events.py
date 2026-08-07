"""Domain events this service publishes (docs/058 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every connector/sync/flow call raises and the caller gets a 400 for a
request that did nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "integration-hub-service"


@default_registry.register
class ConnectorRegisteredEvent(DomainEvent):
    """A new connector instance was registered."""

    event_name: ClassVar[str] = "ConnectorRegistered"


@default_registry.register
class ConnectorInstalledEvent(DomainEvent):
    """A connector was installed at a specific version."""

    event_name: ClassVar[str] = "ConnectorInstalled"


@default_registry.register
class ConnectorEnabledEvent(DomainEvent):
    """A connector was enabled."""

    event_name: ClassVar[str] = "ConnectorEnabled"


@default_registry.register
class ConnectorDisabledEvent(DomainEvent):
    """A connector was disabled."""

    event_name: ClassVar[str] = "ConnectorDisabled"


@default_registry.register
class SynchronizationStartedEvent(DomainEvent):
    """A sync job began running."""

    event_name: ClassVar[str] = "SynchronizationStarted"


@default_registry.register
class SynchronizationCompletedEvent(DomainEvent):
    """A sync job finished, with at least partial success."""

    event_name: ClassVar[str] = "SynchronizationCompleted"


@default_registry.register
class SynchronizationFailedEvent(DomainEvent):
    """A sync job failed outright."""

    event_name: ClassVar[str] = "SynchronizationFailed"


@default_registry.register
class ConnectorHealthChangedEvent(DomainEvent):
    """A connector's own health status changed since its last probe."""

    event_name: ClassVar[str] = "ConnectorHealthChanged"


@default_registry.register
class MarketplaceUpdatedEvent(DomainEvent):
    """A marketplace catalog entry was published, updated, or installed."""

    event_name: ClassVar[str] = "MarketplaceUpdated"


@default_registry.register
class FlowExecutedEvent(DomainEvent):
    """One integration flow run finished -- its own execution history,
    since docs/058's own "DATABASE TABLES" section has no dedicated
    flow-run-history table (see ``ConnectorFlow``'s own docstring)."""

    event_name: ClassVar[str] = "FlowExecuted"


__all__ = [
    "SOURCE_SERVICE",
    "ConnectorDisabledEvent",
    "ConnectorEnabledEvent",
    "ConnectorHealthChangedEvent",
    "ConnectorInstalledEvent",
    "ConnectorRegisteredEvent",
    "FlowExecutedEvent",
    "MarketplaceUpdatedEvent",
    "SynchronizationCompletedEvent",
    "SynchronizationFailedEvent",
    "SynchronizationStartedEvent",
]
