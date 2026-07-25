"""Repository for :class:`app.models.role_permission.RolePermission`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role_permission import RolePermission


class RolePermissionRepository(BaseRepository[RolePermission]):
    """CRUD plus lookup for :class:`RolePermission`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, RolePermission, tenant_scope=tenant_scope)

    async def list_for_role(self, role_id: UUID) -> list[RolePermission]:
        """Every permission grant for *role_id*."""
        stmt = self._base_select().where(RolePermission.role_id == role_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, role_id: UUID, permission_id: UUID) -> RolePermission | None:
        """Return the grant of *permission_id* to *role_id*, or ``None``."""
        stmt = self._base_select().where(
            RolePermission.role_id == role_id, RolePermission.permission_id == permission_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["RolePermissionRepository"]
