"""Configuration management domain events.

Per docs/039 "EVENTS": ConfigurationCreated, ConfigurationUpdated,
ConfigurationApproved, ConfigurationRejected, ConfigurationAssigned,
DriftDetected, ComplianceFailed, RollbackStarted, RollbackCompleted,
BackupCreated, RestoreCompleted. "Integrate with Prompt 020" -- each is
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
class ConfigurationCreatedEvent(DomainEvent):
    """A new configuration profile was created."""

    event_name: ClassVar[str] = "ConfigurationCreated"


@default_registry.register
class ConfigurationUpdatedEvent(DomainEvent):
    """A configuration profile's desired state changed."""

    event_name: ClassVar[str] = "ConfigurationUpdated"


@default_registry.register
class ConfigurationApprovedEvent(DomainEvent):
    """A configuration approval step was approved."""

    event_name: ClassVar[str] = "ConfigurationApproved"


@default_registry.register
class ConfigurationRejectedEvent(DomainEvent):
    """A configuration approval step was rejected."""

    event_name: ClassVar[str] = "ConfigurationRejected"


@default_registry.register
class ConfigurationAssignedEvent(DomainEvent):
    """A configuration profile was assigned to a managed asset."""

    event_name: ClassVar[str] = "ConfigurationAssigned"


@default_registry.register
class DriftDetectedEvent(DomainEvent):
    """A drift between desired and actual state was detected."""

    event_name: ClassVar[str] = "DriftDetected"


@default_registry.register
class ComplianceFailedEvent(DomainEvent):
    """A compliance evaluation failed."""

    event_name: ClassVar[str] = "ComplianceFailed"


@default_registry.register
class RollbackStartedEvent(DomainEvent):
    """A rollback operation began."""

    event_name: ClassVar[str] = "RollbackStarted"


@default_registry.register
class RollbackCompletedEvent(DomainEvent):
    """A rollback operation finished."""

    event_name: ClassVar[str] = "RollbackCompleted"


@default_registry.register
class BackupCreatedEvent(DomainEvent):
    """A configuration backup/snapshot/export was created."""

    event_name: ClassVar[str] = "BackupCreated"


@default_registry.register
class RestoreCompletedEvent(DomainEvent):
    """A restore operation finished."""

    event_name: ClassVar[str] = "RestoreCompleted"


__all__ = [
    "BackupCreatedEvent",
    "ComplianceFailedEvent",
    "ConfigurationApprovedEvent",
    "ConfigurationAssignedEvent",
    "ConfigurationCreatedEvent",
    "ConfigurationRejectedEvent",
    "ConfigurationUpdatedEvent",
    "DriftDetectedEvent",
    "RestoreCompletedEvent",
    "RollbackCompletedEvent",
    "RollbackStartedEvent",
]
