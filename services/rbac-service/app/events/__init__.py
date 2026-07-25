"""Domain events published by the RBAC service."""

from __future__ import annotations

from app.events.rbac_events import (
    AuthorizationDeniedEvent,
    PermissionCreatedEvent,
    PermissionDeletedEvent,
    PermissionUpdatedEvent,
    PolicyCreatedEvent,
    PolicyDeletedEvent,
    PolicyUpdatedEvent,
    RoleAssignedEvent,
    RoleCreatedEvent,
    RoleDeletedEvent,
    RoleRemovedEvent,
    RoleUpdatedEvent,
)

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
