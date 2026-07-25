"""Session lifecycle: create, validate, refresh, expire, revoke, terminate.

Per docs/017_Enterprise_Security_Framework.md.txt "SESSION MANAGEMENT":
idle timeout, absolute timeout, concurrent session limit, device
tracking. Backed by :class:`shared_core.cache.manager.CacheManager`
(Redis) -- sessions are inherently a shared, cross-process concern, the
same reasoning that makes :mod:`shared_core.security.ratelimit` Redis-backed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager
from shared_core.constants.authentication import AuthConstants


@dataclass(frozen=True, slots=True)
class Session:
    """A single authenticated session."""

    session_id: str
    user_id: str
    created_at: datetime
    last_active_at: datetime
    device_id: str | None = None
    ip_address: str | None = None
    revoked: bool = False


def _session_to_dict(session: Session) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "created_at": session.created_at.isoformat(),
        "last_active_at": session.last_active_at.isoformat(),
        "device_id": session.device_id,
        "ip_address": session.ip_address,
        "revoked": session.revoked,
    }


def _session_from_dict(data: dict[str, Any]) -> Session:
    return Session(
        session_id=data["session_id"],
        user_id=data["user_id"],
        created_at=datetime.fromisoformat(data["created_at"]),
        last_active_at=datetime.fromisoformat(data["last_active_at"]),
        device_id=data.get("device_id"),
        ip_address=data.get("ip_address"),
        revoked=data.get("revoked", False),
    )


class SessionManager:
    """Redis-backed session store."""

    def __init__(
        self,
        cache: CacheManager,
        *,
        idle_timeout_seconds: int = AuthConstants.SESSION_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds: int = AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        max_concurrent_sessions: int = AuthConstants.MAX_CONCURRENT_SESSIONS,
    ) -> None:
        self._cache = cache
        self._idle_timeout_seconds = idle_timeout_seconds
        self._absolute_timeout_seconds = absolute_timeout_seconds
        self._max_concurrent_sessions = max_concurrent_sessions

    async def create_session(
        self, *, user_id: str, device_id: str | None = None, ip_address: str | None = None
    ) -> Session:
        """Create a new session, evicting the oldest if the concurrent-session limit is reached."""
        await self._enforce_session_limit(user_id)
        now = datetime.now(UTC)
        session = Session(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=now,
            last_active_at=now,
            device_id=device_id,
            ip_address=ip_address,
        )
        await self._store(session)
        await self._track_user_session(user_id, session.session_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Return the session for *session_id*, whether or not it's still valid."""
        raw = await self._cache.get(self._session_key(session_id))
        return _session_from_dict(raw) if raw else None

    async def validate_session(self, session_id: str) -> Session | None:
        """Return the session if it's active and within both timeouts, else ``None``."""
        session = await self.get_session(session_id)
        if session is None or session.revoked:
            return None
        now = datetime.now(UTC)
        if (now - session.last_active_at).total_seconds() > self._idle_timeout_seconds:
            return None
        if (now - session.created_at).total_seconds() > self._absolute_timeout_seconds:
            return None
        return session

    async def refresh_session(self, session_id: str) -> Session | None:
        """Bump a session's last-active time, extending its idle timeout."""
        session = await self.validate_session(session_id)
        if session is None:
            return None
        refreshed = replace(session, last_active_at=datetime.now(UTC))
        await self._store(refreshed)
        return refreshed

    async def revoke_session(self, session_id: str) -> None:
        """Mark a session revoked, keeping its record (distinguishable from "never existed")."""
        session = await self.get_session(session_id)
        if session is not None:
            await self._store(replace(session, revoked=True))

    async def terminate_session(self, session_id: str) -> None:
        """Permanently remove a session -- unlike :meth:`revoke_session`, no record remains."""
        await self._cache.delete(self._session_key(session_id))

    async def _enforce_session_limit(self, user_id: str) -> None:
        session_ids: list[str] = await self._cache.get(self._user_sessions_key(user_id)) or []
        if len(session_ids) >= self._max_concurrent_sessions:
            oldest_id, session_ids = session_ids[0], session_ids[1:]
            await self.terminate_session(oldest_id)
            await self._cache.set(
                self._user_sessions_key(user_id),
                session_ids,
                ttl_seconds=self._absolute_timeout_seconds,
            )

    async def _track_user_session(self, user_id: str, session_id: str) -> None:
        session_ids: list[str] = await self._cache.get(self._user_sessions_key(user_id)) or []
        session_ids.append(session_id)
        await self._cache.set(
            self._user_sessions_key(user_id),
            session_ids,
            ttl_seconds=self._absolute_timeout_seconds,
        )

    async def _store(self, session: Session) -> None:
        await self._cache.set(
            self._session_key(session.session_id),
            _session_to_dict(session),
            ttl_seconds=self._absolute_timeout_seconds,
        )

    def _session_key(self, session_id: str) -> str:
        return build_cache_key("session", session_id)

    def _user_sessions_key(self, user_id: str) -> str:
        return build_cache_key("user_sessions", user_id)
