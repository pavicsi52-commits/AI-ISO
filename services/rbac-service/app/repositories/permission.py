"""Repository for :class:`app.models.permission.Permission`."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ResourceType
from app.models.permission import Permission


class PermissionRepository(BaseRepository[Permission]):
    """CRUD plus lookup for :class:`Permission`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Permission, tenant_scope=tenant_scope)

    async def get_by_code(self, code: str) -> Permission | None:
        """Return the permission identified by *code*, or ``None``."""
        stmt = self._base_select().where(Permission.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_resource(self, resource: ResourceType) -> list[Permission]:
        """Every permission defined for *resource*."""
        stmt = self._base_select().where(Permission.resource == resource)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, permission_ids: Sequence[UUID]) -> list[Permission]:
        """Every permission whose id is in *permission_ids*."""
        stmt = self._base_select().where(Permission.id.in_(permission_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[Permission]:
        """Every permission ("Permission Management": list)."""
        result = await self._session.execute(self._base_select())
        return list(result.scalars().all())


__all__ = ["PermissionRepository"]
