"""Repository for :class:`app.models.role.Role`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role


class RoleRepository(BaseRepository[Role]):
    """CRUD plus lookup/hierarchy queries for :class:`Role`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Role, tenant_scope=tenant_scope)

    async def get_by_code(self, code: str) -> Role | None:
        """Return the role identified by *code*, or ``None``."""
        stmt = self._base_select().where(Role.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_children(self, parent_role_id: UUID) -> list[Role]:
        """Every role whose ``parent_role_id`` is *parent_role_id*."""
        stmt = self._base_select().where(Role.parent_role_id == parent_role_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[Role]:
        """Every role, for hierarchy-graph construction and listing."""
        result = await self._session.execute(self._base_select())
        return list(result.scalars().all())


__all__ = ["RoleRepository"]
