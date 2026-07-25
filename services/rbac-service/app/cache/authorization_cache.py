"""Authorization cache: the "User Permission Matrix", cached.

Per docs/032 "CACHING": Permissions, Roles, Policy Results,
Authorization Decisions, User Permission Matrix. "Integrate with
Prompt 019." Reuses :class:`shared_core.cache.manager.CacheManager`
directly, the same primitive
``services/user-management-service``'s ``UserCacheService`` wraps for
its own hot-read-path caching -- short TTL plus explicit invalidation
on a direct write to *this* user's own role assignments, rather than a
reverse index tracking every user potentially affected by a role or
permission definition changing (out of scope for this prompt; TTL
expiry bounds the staleness window in that case).
"""

from __future__ import annotations

from uuid import UUID

from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager


class AuthorizationCacheService:
    """Caches one user/scope's computed effective-permission-code list."""

    def __init__(self, cache: CacheManager, *, ttl_seconds: int) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def _key(self, user_id: UUID, organization_id: UUID, project_id: UUID | None) -> str:
        return build_cache_key(
            "user_permissions", str(user_id), str(organization_id), str(project_id or "-")
        )

    async def get_permissions(
        self, user_id: UUID, organization_id: UUID, project_id: UUID | None
    ) -> list[str] | None:
        """Return the cached permission-code list for this exact user/scope, if any."""
        return await self._cache.get(self._key(user_id, organization_id, project_id))

    async def set_permissions(
        self,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID | None,
        permissions: list[str],
    ) -> None:
        """Cache *permissions* for this user/scope ("User Permission Matrix")."""
        await self._cache.set(
            self._key(user_id, organization_id, project_id),
            permissions,
            ttl_seconds=self._ttl_seconds,
        )

    async def invalidate_user(
        self, user_id: UUID, organization_id: UUID, project_id: UUID | None = None
    ) -> None:
        """Evict *user_id*'s cached matrix after a direct role-assignment change."""
        await self._cache.delete(self._key(user_id, organization_id, project_id))


__all__ = ["AuthorizationCacheService"]
