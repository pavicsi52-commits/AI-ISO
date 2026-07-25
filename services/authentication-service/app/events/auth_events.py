"""Authentication domain events.

Per docs/030 "EVENTS": UserLoggedIn, UserLoggedOut, PasswordChanged,
PasswordResetRequested, PasswordResetCompleted, EmailVerified,
SessionCreated, SessionExpired, ApiKeyCreated, ApiKeyRevoked,
MfaEnabled, MfaDisabled, AccountLocked, AccountUnlocked. "Integrate
with Prompt 020" -- each is a :class:`shared_core.events.base.DomainEvent`
(a business fact other services may subscribe to), published via
:class:`shared_core.events.manager.EventManager`.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class UserLoggedInEvent(DomainEvent):
    """A user successfully logged in."""

    event_name: ClassVar[str] = "UserLoggedIn"


@default_registry.register
class UserLoggedOutEvent(DomainEvent):
    """A user logged out."""

    event_name: ClassVar[str] = "UserLoggedOut"


@default_registry.register
class PasswordChangedEvent(DomainEvent):
    """A user's password was changed."""

    event_name: ClassVar[str] = "PasswordChanged"


@default_registry.register
class PasswordResetRequestedEvent(DomainEvent):
    """A user requested a password reset."""

    event_name: ClassVar[str] = "PasswordResetRequested"


@default_registry.register
class PasswordResetCompletedEvent(DomainEvent):
    """A user completed a password reset."""

    event_name: ClassVar[str] = "PasswordResetCompleted"


@default_registry.register
class EmailVerifiedEvent(DomainEvent):
    """A user verified their email address."""

    event_name: ClassVar[str] = "EmailVerified"


@default_registry.register
class SessionCreatedEvent(DomainEvent):
    """A new session was created."""

    event_name: ClassVar[str] = "SessionCreated"


@default_registry.register
class SessionExpiredEvent(DomainEvent):
    """A session expired or was terminated."""

    event_name: ClassVar[str] = "SessionExpired"


@default_registry.register
class ApiKeyCreatedEvent(DomainEvent):
    """A new API key was created."""

    event_name: ClassVar[str] = "ApiKeyCreated"


@default_registry.register
class ApiKeyRevokedEvent(DomainEvent):
    """An API key was revoked."""

    event_name: ClassVar[str] = "ApiKeyRevoked"


@default_registry.register
class MfaEnabledEvent(DomainEvent):
    """A user enabled MFA."""

    event_name: ClassVar[str] = "MfaEnabled"


@default_registry.register
class MfaDisabledEvent(DomainEvent):
    """A user disabled MFA."""

    event_name: ClassVar[str] = "MfaDisabled"


@default_registry.register
class AccountLockedEvent(DomainEvent):
    """A user account was locked."""

    event_name: ClassVar[str] = "AccountLocked"


@default_registry.register
class AccountUnlockedEvent(DomainEvent):
    """A user account was unlocked."""

    event_name: ClassVar[str] = "AccountUnlocked"


__all__ = [
    "AccountLockedEvent",
    "AccountUnlockedEvent",
    "ApiKeyCreatedEvent",
    "ApiKeyRevokedEvent",
    "EmailVerifiedEvent",
    "MfaDisabledEvent",
    "MfaEnabledEvent",
    "PasswordChangedEvent",
    "PasswordResetCompletedEvent",
    "PasswordResetRequestedEvent",
    "SessionCreatedEvent",
    "SessionExpiredEvent",
    "UserLoggedInEvent",
    "UserLoggedOutEvent",
]
