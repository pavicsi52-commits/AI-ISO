"""RBAC domain events.

Per docs/032 "EVENTS": RoleCreated, RoleUpdated, RoleDeleted,
PermissionCreated, PermissionUpdated, PermissionDeleted, RoleAssigned,
RoleRemoved, PolicyCreated, PolicyUpdated, PolicyDeleted,
AuthorizationDenied. "Integrate with Prompt 020" -- each is a
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
class RoleCreatedEvent(DomainEvent):
    """A new role was created."""

    event_name: ClassVar[str] = "RoleCreated"


@default_registry.register
class RoleUpdatedEvent(DomainEvent):
    """A role's fields were updated."""

    event_name: ClassVar[str] = "RoleUpdated"


@default_registry.register
class RoleDeletedEvent(DomainEvent):
    """A role was (soft-)deleted."""

    event_name: ClassVar[str] = "RoleDeleted"


@default_registry.register
class PermissionCreatedEvent(DomainEvent):
    """A new permission was created."""

    event_name: ClassVar[str] = "PermissionCreated"


@default_registry.register
class PermissionUpdatedEvent(DomainEvent):
    """A permission's fields were updated."""

    event_name: ClassVar[str] = "PermissionUpdated"


@default_registry.register
class PermissionDeletedEvent(DomainEvent):
    """A permission was (soft-)deleted."""

    event_name: ClassVar[str] = "PermissionDeleted"


@default_registry.register
class RoleAssignedEvent(DomainEvent):
    """A role was assigned to a user."""

    event_name: ClassVar[str] = "RoleAssigned"


@default_registry.register
class RoleRemovedEvent(DomainEvent):
    """A role assignment was removed from a user."""

    event_name: ClassVar[str] = "RoleRemoved"


@default_registry.register
class PolicyCreatedEvent(DomainEvent):
    """A new authorization policy was created."""

    event_name: ClassVar[str] = "PolicyCreated"


@default_registry.register
class PolicyUpdatedEvent(DomainEvent):
    """An authorization policy's fields were updated."""

    event_name: ClassVar[str] = "PolicyUpdated"


@default_registry.register
class PolicyDeletedEvent(DomainEvent):
    """An authorization policy was (soft-)deleted."""

    event_name: ClassVar[str] = "PolicyDeleted"


@default_registry.register
class AuthorizationDeniedEvent(DomainEvent):
    """An authorization evaluation resulted in a deny decision."""

    event_name: ClassVar[str] = "AuthorizationDenied"


__all__ = [
    "AuthorizationDeniedEvent",
    "PermissionCreatedEvent",
    "PermissionDeletedEvent",
    "PermissionUpdatedEvent",
    "PolicyCreatedEvent",
    "PolicyDeletedEvent",
    "PolicyUpdatedEvent",
    "RoleAssignedEvent",
    "RoleCreatedEvent",
    "RoleDeletedEvent",
    "RoleRemovedEvent",
    "RoleUpdatedEvent",
]
