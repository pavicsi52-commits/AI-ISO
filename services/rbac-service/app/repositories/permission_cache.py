"""Repository for :class:`app.models.permission_cache.PermissionCacheEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission_cache import PermissionCacheEntry


class PermissionCacheRepository(BaseRepository[PermissionCacheEntry]):
    """CRUD plus lookup for :class:`PermissionCacheEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PermissionCacheEntry, tenant_scope=tenant_scope)

    async def get_for_user(
        self, user_id: UUID, organization_id: UUID, project_id: UUID | None
    ) -> PermissionCacheEntry | None:
        """Return the last-computed entry for this exact user/scope, or ``None``."""
        stmt = self._base_select().where(
            PermissionCacheEntry.user_id == user_id,
            PermissionCacheEntry.organization_id == organization_id,
            PermissionCacheEntry.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["PermissionCacheRepository"]
