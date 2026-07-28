"""Repository for :class:`app.models.dashboard_permission.DashboardPermission`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_permission import DashboardPermission


class DashboardPermissionRepository(BaseRepository[DashboardPermission]):
    """CRUD plus lookups for :class:`DashboardPermission`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardPermission, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardPermission]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardPermission.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_dashboard(self, dashboard_id: UUID) -> list[DashboardPermission]:
        """Every standing role permission on one dashboard."""
        stmt = self._base_select().where(
            DashboardPermission.dashboard_id == dashboard_id,
            DashboardPermission.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_role(self, dashboard_id: UUID, role: str) -> DashboardPermission | None:
        """One role's permission on one dashboard."""
        stmt = self._base_select().where(
            DashboardPermission.dashboard_id == dashboard_id,
            DashboardPermission.role == role,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["DashboardPermissionRepository"]
