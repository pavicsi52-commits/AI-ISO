"""User management domain events.

Per docs/031 "EVENTS": UserCreated, UserUpdated, UserDeleted,
UserActivated, UserDeactivated, UserInvited, InvitationAccepted,
ProfileUpdated, PreferencesUpdated, AvatarUpdated, UserImported,
UserExported. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent` (a business fact other
services may subscribe to), published via
:class:`shared_core.events.manager.EventManager`. Registered with
:data:`shared_core.events.registry.default_registry` at import time
(the same "@decorator, imported once at startup" idiom
``services/authentication-service`` established) -- an unregistered
event fails validation the moment it's published, not silently.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class UserCreatedEvent(DomainEvent):
    """A new user was created."""

    event_name: ClassVar[str] = "UserCreated"


@default_registry.register
class UserUpdatedEvent(DomainEvent):
    """A user's core fields were updated."""

    event_name: ClassVar[str] = "UserUpdated"


@default_registry.register
class UserDeletedEvent(DomainEvent):
    """A user was (soft-)deleted."""

    event_name: ClassVar[str] = "UserDeleted"


@default_registry.register
class UserActivatedEvent(DomainEvent):
    """A user's status transitioned to active."""

    event_name: ClassVar[str] = "UserActivated"


@default_registry.register
class UserDeactivatedEvent(DomainEvent):
    """A user's status transitioned away from active."""

    event_name: ClassVar[str] = "UserDeactivated"


@default_registry.register
class UserInvitedEvent(DomainEvent):
    """A new invitation was extended."""

    event_name: ClassVar[str] = "UserInvited"


@default_registry.register
class InvitationAcceptedEvent(DomainEvent):
    """An invitation was accepted."""

    event_name: ClassVar[str] = "InvitationAccepted"


@default_registry.register
class ProfileUpdatedEvent(DomainEvent):
    """A user's profile was updated."""

    event_name: ClassVar[str] = "ProfileUpdated"


@default_registry.register
class PreferencesUpdatedEvent(DomainEvent):
    """A user's preferences were updated."""

    event_name: ClassVar[str] = "PreferencesUpdated"


@default_registry.register
class AvatarUpdatedEvent(DomainEvent):
    """A user's avatar was uploaded, replaced, or removed."""

    event_name: ClassVar[str] = "AvatarUpdated"


@default_registry.register
class UserImportedEvent(DomainEvent):
    """A bulk user-import job completed."""

    event_name: ClassVar[str] = "UserImported"


@default_registry.register
class UserExportedEvent(DomainEvent):
    """A bulk user-export job completed."""

    event_name: ClassVar[str] = "UserExported"


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
