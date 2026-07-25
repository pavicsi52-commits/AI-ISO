"""Session lifecycle.

Per docs/027_Enterprise_Connector_SDK.md.txt "SESSION MANAGEMENT":
Create, Refresh, Expire, Terminate, Idle Timeout, Maximum Lifetime.
("Reconnect" is :mod:`~shared_core.connectors.base`'s
``BaseConnector.reconnect()``, which builds a fresh :class:`Session`
via this module rather than this module owning reconnection itself.)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from shared_core.connectors.constants import (
    DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
    DEFAULT_SESSION_MAX_LIFETIME_SECONDS,
)


def new_session_id() -> str:
    """Generate a new, unique session id."""
    return str(uuid.uuid4())


@dataclass(slots=True)
class Session:
    """One connector's live session against a target ("Create")."""

    session_id: str = field(default_factory=new_session_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    idle_timeout_seconds: float = DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS
    max_lifetime_seconds: float = DEFAULT_SESSION_MAX_LIFETIME_SECONDS
    terminated: bool = False

    def touch(self) -> None:
        """Mark the session as just used ("Refresh")."""
        self.last_used_at = datetime.now(UTC)

    def is_idle_expired(self, *, now: datetime | None = None) -> bool:
        """Whether the session has been idle past ``idle_timeout_seconds`` ("Idle Timeout")."""
        moment = now or datetime.now(UTC)
        return (moment - self.last_used_at).total_seconds() > self.idle_timeout_seconds

    def is_lifetime_expired(self, *, now: datetime | None = None) -> bool:
        """Whether the session is older than ``max_lifetime_seconds`` ("Maximum Lifetime")."""
        moment = now or datetime.now(UTC)
        return (moment - self.created_at).total_seconds() > self.max_lifetime_seconds

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether the session is expired by termination, idle timeout, or lifetime ("Expire")."""
        return self.terminated or self.is_idle_expired(now=now) or self.is_lifetime_expired(now=now)

    def terminate(self) -> None:
        """Mark the session as permanently ended ("Terminate")."""
        self.terminated = True


__all__ = ["Session", "new_session_id"]
