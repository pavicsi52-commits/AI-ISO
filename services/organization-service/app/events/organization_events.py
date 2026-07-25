"""Organization domain events.

Per docs/033 "EVENTS": OrganizationCreated, OrganizationUpdated,
OrganizationDeleted, OrganizationActivated, OrganizationSuspended,
DepartmentCreated, DepartmentDeleted, TeamCreated, SubscriptionChanged,
QuotaExceeded, LicenseExpired. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`. Registered with
:data:`shared_core.events.registry.default_registry` at import time
(the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established) -- an unregistered event fails validation
the moment it's published, not silently.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class OrganizationCreatedEvent(DomainEvent):
    """A new organization was created."""

    event_name: ClassVar[str] = "OrganizationCreated"


@default_registry.register
class OrganizationUpdatedEvent(DomainEvent):
    """An organization's fields were updated."""

    event_name: ClassVar[str] = "OrganizationUpdated"


@default_registry.register
class OrganizationDeletedEvent(DomainEvent):
    """An organization was (soft-)deleted."""

    event_name: ClassVar[str] = "OrganizationDeleted"


@default_registry.register
class OrganizationActivatedEvent(DomainEvent):
    """An organization's status transitioned to active."""

    event_name: ClassVar[str] = "OrganizationActivated"


@default_registry.register
class OrganizationSuspendedEvent(DomainEvent):
    """An organization's status transitioned to suspended."""

    event_name: ClassVar[str] = "OrganizationSuspended"


@default_registry.register
class DepartmentCreatedEvent(DomainEvent):
    """A new department was created."""

    event_name: ClassVar[str] = "DepartmentCreated"


@default_registry.register
class DepartmentDeletedEvent(DomainEvent):
    """A department was (soft-)deleted."""

    event_name: ClassVar[str] = "DepartmentDeleted"


@default_registry.register
class TeamCreatedEvent(DomainEvent):
    """A new team was created."""

    event_name: ClassVar[str] = "TeamCreated"


@default_registry.register
class SubscriptionChangedEvent(DomainEvent):
    """An organization's subscription plan or status changed."""

    event_name: ClassVar[str] = "SubscriptionChanged"


@default_registry.register
class QuotaExceededEvent(DomainEvent):
    """An organization exceeded one of its configured quotas."""

    event_name: ClassVar[str] = "QuotaExceeded"


@default_registry.register
class LicenseExpiredEvent(DomainEvent):
    """An organization's license expired."""

    event_name: ClassVar[str] = "LicenseExpired"


__all__ = [
    "DepartmentCreatedEvent",
    "DepartmentDeletedEvent",
    "LicenseExpiredEvent",
    "OrganizationActivatedEvent",
    "OrganizationCreatedEvent",
    "OrganizationDeletedEvent",
    "OrganizationSuspendedEvent",
    "OrganizationUpdatedEvent",
    "QuotaExceededEvent",
    "SubscriptionChangedEvent",
    "TeamCreatedEvent",
]
