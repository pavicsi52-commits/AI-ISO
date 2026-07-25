"""Asset management domain events.

Per docs/038 "EVENTS": ManagedAssetCreated, AssetAssigned,
OwnershipTransferred, MaintenanceScheduled, MaintenanceCompleted,
WarrantyExpired, ContractExpired, ComplianceFailed, RiskScoreChanged,
AssetRetired, LifecycleChanged. "Integrate with Prompt 020" -- each is
a :class:`shared_core.events.base.DomainEvent`, published via
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
class ManagedAssetCreatedEvent(DomainEvent):
    """A new managed asset was registered."""

    event_name: ClassVar[str] = "ManagedAssetCreated"


@default_registry.register
class AssetAssignedEvent(DomainEvent):
    """A managed asset was assigned to a principal."""

    event_name: ClassVar[str] = "AssetAssigned"


@default_registry.register
class OwnershipTransferredEvent(DomainEvent):
    """A managed asset's ownership role changed holder."""

    event_name: ClassVar[str] = "OwnershipTransferred"


@default_registry.register
class MaintenanceScheduledEvent(DomainEvent):
    """A maintenance activity was scheduled."""

    event_name: ClassVar[str] = "MaintenanceScheduled"


@default_registry.register
class MaintenanceCompletedEvent(DomainEvent):
    """A maintenance activity was completed."""

    event_name: ClassVar[str] = "MaintenanceCompleted"


@default_registry.register
class WarrantyExpiredEvent(DomainEvent):
    """A managed asset's warranty coverage expired."""

    event_name: ClassVar[str] = "WarrantyExpired"


@default_registry.register
class ContractExpiredEvent(DomainEvent):
    """A managed asset's contract expired."""

    event_name: ClassVar[str] = "ContractExpired"


@default_registry.register
class ComplianceFailedEvent(DomainEvent):
    """A compliance evaluation failed."""

    event_name: ClassVar[str] = "ComplianceFailed"


@default_registry.register
class RiskScoreChangedEvent(DomainEvent):
    """A managed asset's risk score changed."""

    event_name: ClassVar[str] = "RiskScoreChanged"


@default_registry.register
class AssetRetiredEvent(DomainEvent):
    """A managed asset was retired."""

    event_name: ClassVar[str] = "AssetRetired"


@default_registry.register
class LifecycleChangedEvent(DomainEvent):
    """A managed asset's lifecycle state changed."""

    event_name: ClassVar[str] = "LifecycleChanged"


__all__ = [
    "AssetAssignedEvent",
    "AssetRetiredEvent",
    "ComplianceFailedEvent",
    "ContractExpiredEvent",
    "LifecycleChangedEvent",
    "MaintenanceCompletedEvent",
    "MaintenanceScheduledEvent",
    "ManagedAssetCreatedEvent",
    "OwnershipTransferredEvent",
    "RiskScoreChangedEvent",
    "WarrantyExpiredEvent",
]
