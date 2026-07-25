"""Response-level caching for hot read paths.

Per docs/031 "PERFORMANCE": "Cache Integration". Caches at the
serialized-response-DTO level (a plain ``dict``), not the SQLAlchemy
entity -- ORM objects aren't safely round-trippable through a JSON
cache without a bespoke (de)serializer, and caching the exact shape a
client receives is the more common, lower-risk production pattern
anyway. Reuses :class:`shared_core.cache.manager.CacheManager`
directly (the same primitive ``services/authentication-service``'s
``SessionManager`` wraps for its own Redis-backed state).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager

_USER_DETAIL_TTL_SECONDS = 60


class UserCacheService:
    """Caches ``GET /users/{id}``'s serialized response, invalidated on any write."""

    def __init__(self, cache: CacheManager) -> None:
        self._cache = cache

    def _key(self, user_id: UUID) -> str:
        return build_cache_key("user_detail", str(user_id))

    async def get(self, user_id: UUID) -> dict[str, Any] | None:
        """Return the cached serialized user, or ``None`` on a cache miss."""
        return await self._cache.get(self._key(user_id))

    async def set(self, user_id: UUID, data: dict[str, Any]) -> None:
        """Cache *data* for *user_id* ("Cache Integration")."""
        await self._cache.set(self._key(user_id), data, ttl_seconds=_USER_DETAIL_TTL_SECONDS)

    async def invalidate(self, user_id: UUID) -> None:
        """Evict *user_id*'s cached response after any write."""
        await self._cache.delete(self._key(user_id))


__all__ = ["UserCacheService"]
