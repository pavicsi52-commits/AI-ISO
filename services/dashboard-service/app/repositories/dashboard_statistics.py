"""Repository for :class:`app.models.dashboard_statistics.DashboardStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_statistics import DashboardStatistics


class DashboardStatisticsRepository(BaseRepository[DashboardStatistics]):
    """CRUD plus lookups for :class:`DashboardStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardStatistics, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardStatistics]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_org(self, organization_id: UUID) -> DashboardStatistics | None:
        """Return *organization_id*'s cached rollup, or ``None``."""
        stmt = self._base_select().where(
            DashboardStatistics.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["DashboardStatisticsRepository"]
