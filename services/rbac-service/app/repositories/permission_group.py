"""Repository for :class:`app.models.permission_group.PermissionGroup`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission_group import PermissionGroup


class PermissionGroupRepository(BaseRepository[PermissionGroup]):
    """CRUD plus lookup for :class:`PermissionGroup`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PermissionGroup, tenant_scope=tenant_scope)

    async def get_by_code(self, code: str) -> PermissionGroup | None:
        """Return the permission group identified by *code*, or ``None``."""
        stmt = self._base_select().where(PermissionGroup.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PermissionGroup]:
        """Every permission group."""
        result = await self._session.execute(self._base_select())
        return list(result.scalars().all())


__all__ = ["PermissionGroupRepository"]
