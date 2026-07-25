"""Domain events published by the user management service."""

from __future__ import annotations

from app.events.user_events import (
    AvatarUpdatedEvent,
    InvitationAcceptedEvent,
    PreferencesUpdatedEvent,
    ProfileUpdatedEvent,
    UserActivatedEvent,
    UserCreatedEvent,
    UserDeactivatedEvent,
    UserDeletedEvent,
    UserExportedEvent,
    UserImportedEvent,
    UserInvitedEvent,
    UserUpdatedEvent,
)

__all__ = [
    "AvatarUpdatedEvent",
    "InvitationAcceptedEvent",
    "PreferencesUpdatedEvent",
    "ProfileUpdatedEvent",
    "UserActivatedEvent",
    "UserCreatedEvent",
    "UserDeactivatedEvent",
    "UserDeletedEvent",
    "UserExportedEvent",
    "UserImportedEvent",
    "UserInvitedEvent",
    "UserUpdatedEvent",
]
