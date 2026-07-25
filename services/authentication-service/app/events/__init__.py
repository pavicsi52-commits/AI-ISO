"""Domain events published by the authentication service."""

from __future__ import annotations

from app.events.auth_events import (
    AccountLockedEvent,
    AccountUnlockedEvent,
    ApiKeyCreatedEvent,
    ApiKeyRevokedEvent,
    EmailVerifiedEvent,
    MfaDisabledEvent,
    MfaEnabledEvent,
    PasswordChangedEvent,
    PasswordResetCompletedEvent,
    PasswordResetRequestedEvent,
    SessionCreatedEvent,
    SessionExpiredEvent,
    UserLoggedInEvent,
    UserLoggedOutEvent,
)

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
