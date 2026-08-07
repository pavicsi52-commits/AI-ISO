"""Domain events this service publishes (docs/059 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that
decorator every plugin/installation/marketplace call raises and the
caller gets a 400 for a request that did nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "plugin-marketplace-service"


@default_registry.register
class PluginRegisteredEvent(DomainEvent):
    """A new plugin definition was registered."""

    event_name: ClassVar[str] = "PluginRegistered"


@default_registry.register
class PluginPublishedEvent(DomainEvent):
    """A plugin version was published to the marketplace."""

    event_name: ClassVar[str] = "PluginPublished"


@default_registry.register
class PluginInstalledEvent(DomainEvent):
    """An organization installed a plugin."""

    event_name: ClassVar[str] = "PluginInstalled"


@default_registry.register
class PluginActivatedEvent(DomainEvent):
    """An installed plugin instance was activated."""

    event_name: ClassVar[str] = "PluginActivated"


@default_registry.register
class PluginUpgradedEvent(DomainEvent):
    """An installed plugin instance was upgraded to a newer version."""

    event_name: ClassVar[str] = "PluginUpgraded"


@default_registry.register
class PluginRolledBackEvent(DomainEvent):
    """An installed plugin instance was rolled back to an older version."""

    event_name: ClassVar[str] = "PluginRolledBack"


@default_registry.register
class PluginDisabledEvent(DomainEvent):
    """An installed plugin instance was disabled."""

    event_name: ClassVar[str] = "PluginDisabled"


@default_registry.register
class PluginRemovedEvent(DomainEvent):
    """An installed plugin instance was removed."""

    event_name: ClassVar[str] = "PluginRemoved"


@default_registry.register
class MarketplaceUpdatedEvent(DomainEvent):
    """A marketplace listing was created, published, featured, or removed."""

    event_name: ClassVar[str] = "MarketplaceUpdated"


__all__ = [
    "SOURCE_SERVICE",
    "MarketplaceUpdatedEvent",
    "PluginActivatedEvent",
    "PluginDisabledEvent",
    "PluginInstalledEvent",
    "PluginPublishedEvent",
    "PluginRegisteredEvent",
    "PluginRemovedEvent",
    "PluginRolledBackEvent",
    "PluginUpgradedEvent",
]
