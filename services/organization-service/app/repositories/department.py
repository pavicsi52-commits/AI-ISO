"""Repository for :class:`app.models.department.Department`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department


class DepartmentRepository(BaseRepository[Department]):
    """CRUD plus lookup/hierarchy queries for :class:`Department`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Department, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[Department]:
        """Every department belonging to *organization_id*."""
        stmt = self._base_select().where(Department.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self, parent_department_id: UUID) -> list[Department]:
        """Every department whose ``parent_department_id`` is *parent_department_id*."""
        stmt = self._base_select().where(Department.parent_department_id == parent_department_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DepartmentRepository"]
