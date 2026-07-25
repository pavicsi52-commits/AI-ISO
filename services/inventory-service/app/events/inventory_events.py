"""Inventory domain events.

Per docs/036 "EVENTS": AssetCreated, AssetUpdated, AssetDeleted,
AssetImported, AssetExported, AssetHealthChanged, AssetMoved,
AssetOwnerChanged, RelationshipCreated, RelationshipDeleted,
InventorySynchronized. "Integrate with Prompt 020" -- each is a
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
class AssetCreatedEvent(DomainEvent):
    """A new asset was registered."""

    event_name: ClassVar[str] = "AssetCreated"


@default_registry.register
class AssetUpdatedEvent(DomainEvent):
    """An asset's fields were updated."""

    event_name: ClassVar[str] = "AssetUpdated"


@default_registry.register
class AssetDeletedEvent(DomainEvent):
    """An asset was (soft-)deleted."""

    event_name: ClassVar[str] = "AssetDeleted"


@default_registry.register
class AssetImportedEvent(DomainEvent):
    """A bulk asset import job completed."""

    event_name: ClassVar[str] = "AssetImported"


@default_registry.register
class AssetExportedEvent(DomainEvent):
    """A bulk asset export job completed."""

    event_name: ClassVar[str] = "AssetExported"


@default_registry.register
class AssetHealthChangedEvent(DomainEvent):
    """An asset's health status changed."""

    event_name: ClassVar[str] = "AssetHealthChanged"


@default_registry.register
class AssetMovedEvent(DomainEvent):
    """An asset's location changed."""

    event_name: ClassVar[str] = "AssetMoved"


@default_registry.register
class AssetOwnerChangedEvent(DomainEvent):
    """An asset's ownership assignment changed."""

    event_name: ClassVar[str] = "AssetOwnerChanged"


@default_registry.register
class RelationshipCreatedEvent(DomainEvent):
    """A relationship edge was created between two assets."""

    event_name: ClassVar[str] = "RelationshipCreated"


@default_registry.register
class RelationshipDeletedEvent(DomainEvent):
    """A relationship edge was deleted."""

    event_name: ClassVar[str] = "RelationshipDeleted"


@default_registry.register
class InventorySynchronizedEvent(DomainEvent):
    """A synchronization pass reconciled inventory state."""

    event_name: ClassVar[str] = "InventorySynchronized"


__all__ = [
    "AssetCreatedEvent",
    "AssetDeletedEvent",
    "AssetExportedEvent",
    "AssetHealthChangedEvent",
    "AssetImportedEvent",
    "AssetMovedEvent",
    "AssetOwnerChangedEvent",
    "AssetUpdatedEvent",
    "InventorySynchronizedEvent",
    "RelationshipCreatedEvent",
    "RelationshipDeletedEvent",
]
