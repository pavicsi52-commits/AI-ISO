"""Session Cache.

Per docs/019_Enterprise_Cache_Framework.md.txt "SESSION CACHE": Store
Sessions, JWT Metadata, Refresh Tokens, User Context, Tenant Context, Idle
Timeout, Session Expiration.

Generic session-data storage keyed by an opaque session ID -- data-shape-
agnostic, unlike Prompt 017's
:class:`shared_core.security.sessions.SessionManager` (which owns the
specific ``Session``/``SecurityContext`` shape for authentication). Built
on the same :class:`~shared_core.cache.manager.CacheManager` primitive;
new call sites that need a keyed, idle-timeout-bearing cache entry for
*any* short-lived state -- not just an auth session -- should prefer this
one.
"""

from __future__ import annotations

from typing import Any

from shared_core.cache.constants import (
    DEFAULT_SESSION_ABSOLUTE_TIMEOUT_SECONDS,
    DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
)
from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager


class SessionCache:
    """Idle-timeout-bearing key/value storage for session-shaped data."""

    def __init__(
        self,
        cache: CacheManager,
        *,
        idle_timeout_seconds: int = DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds: int = DEFAULT_SESSION_ABSOLUTE_TIMEOUT_SECONDS,
    ) -> None:
        self._cache = cache
        self._idle_timeout_seconds = idle_timeout_seconds
        self._absolute_timeout_seconds = absolute_timeout_seconds

    def _key(self, session_id: str) -> str:
        return build_cache_key("session", session_id)

    async def store(self, session_id: str, data: dict[str, Any]) -> None:
        """Store *data* under *session_id*, bounded by the absolute session timeout."""
        await self._cache.set(
            self._key(session_id), data, ttl_seconds=self._absolute_timeout_seconds
        )

    async def get(self, session_id: str, *, touch: bool = True) -> dict[str, Any] | None:
        """Return the session's stored data.

        Refreshes the idle-timeout TTL on access ("Sliding TTL") unless
        *touch* is ``False`` -- pass ``False`` for calls that merely peek
        at session state without counting as user activity.
        """
        data = await self._cache.get(self._key(session_id))
        if data is not None and touch:
            await self._cache.touch(self._key(session_id), ttl_seconds=self._idle_timeout_seconds)
        return data

    async def extend(self, session_id: str, *, ttl_seconds: int | None = None) -> bool:
        """Explicitly refresh a session's TTL. Returns whether the session existed."""
        return await self._cache.touch(
            self._key(session_id), ttl_seconds=ttl_seconds or self._idle_timeout_seconds
        )

    async def revoke(self, session_id: str) -> None:
        """Immediately expire a session ("Session Expiration")."""
        await self._cache.delete(self._key(session_id))


class RefreshTokenCache:
    """Refresh-token metadata storage, keyed by token identifier (``jti``).

    Kept separate from :class:`SessionCache` -- a refresh token often
    outlives the session that issued it (e.g. "remember me").
    """

    def __init__(
        self, cache: CacheManager, *, ttl_seconds: int = DEFAULT_SESSION_ABSOLUTE_TIMEOUT_SECONDS
    ) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def _key(self, token_id: str) -> str:
        return build_cache_key("refresh_token", token_id)

    async def store(self, token_id: str, metadata: dict[str, Any]) -> None:
        """Store refresh-token metadata (user ID, issued-at, device info, ...)."""
        await self._cache.set(self._key(token_id), metadata, ttl_seconds=self._ttl_seconds)

    async def get(self, token_id: str) -> dict[str, Any] | None:
        """Return a refresh token's stored metadata, or ``None`` if unknown/expired/revoked."""
        return await self._cache.get(self._key(token_id))

    async def revoke(self, token_id: str) -> None:
        """Revoke a refresh token immediately."""
        await self._cache.delete(self._key(token_id))


__all__ = ["RefreshTokenCache", "SessionCache"]
