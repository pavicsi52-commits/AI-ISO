"""Discovery domain events.

Per docs/037 "EVENTS": DiscoveryStarted, DiscoveryCompleted,
DiscoveryFailed, AssetDiscovered, AssetUpdated, RelationshipDiscovered,
TopologyUpdated, DiscoveryCancelled, DiscoveryProfileCreated,
DiscoveryScheduleTriggered. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`. Registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class DiscoveryStartedEvent(DomainEvent):
    """A discovery job started running."""

    event_name: ClassVar[str] = "DiscoveryStarted"


@default_registry.register
class DiscoveryCompletedEvent(DomainEvent):
    """A discovery job finished successfully."""

    event_name: ClassVar[str] = "DiscoveryCompleted"


@default_registry.register
class DiscoveryFailedEvent(DomainEvent):
    """A discovery job failed."""

    event_name: ClassVar[str] = "DiscoveryFailed"


@default_registry.register
class AssetDiscoveredEvent(DomainEvent):
    """A new asset was discovered."""

    event_name: ClassVar[str] = "AssetDiscovered"


@default_registry.register
class AssetUpdatedEvent(DomainEvent):
    """A previously-discovered asset's fields changed."""

    event_name: ClassVar[str] = "AssetUpdated"


@default_registry.register
class RelationshipDiscoveredEvent(DomainEvent):
    """A relationship edge was discovered between two assets."""

    event_name: ClassVar[str] = "RelationshipDiscovered"


@default_registry.register
class TopologyUpdatedEvent(DomainEvent):
    """A discovery job's findings updated the known topology."""

    event_name: ClassVar[str] = "TopologyUpdated"


@default_registry.register
class DiscoveryCancelledEvent(DomainEvent):
    """A discovery job was cancelled."""

    event_name: ClassVar[str] = "DiscoveryCancelled"


@default_registry.register
class DiscoveryProfileCreatedEvent(DomainEvent):
    """A new discovery profile was created."""

    event_name: ClassVar[str] = "DiscoveryProfileCreated"


@default_registry.register
class DiscoveryScheduleTriggeredEvent(DomainEvent):
    """A discovery schedule fired, queuing a new job."""

    event_name: ClassVar[str] = "DiscoveryScheduleTriggered"


__all__ = [
    "AssetDiscoveredEvent",
    "AssetUpdatedEvent",
    "DiscoveryCancelledEvent",
    "DiscoveryCompletedEvent",
    "DiscoveryFailedEvent",
    "DiscoveryProfileCreatedEvent",
    "DiscoveryScheduleTriggeredEvent",
    "DiscoveryStartedEvent",
    "RelationshipDiscoveredEvent",
    "TopologyUpdatedEvent",
]
