"""Repository for :class:`app.models.dashboard_history.DashboardHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_history import DashboardHistory


class DashboardHistoryRepository(BaseRepository[DashboardHistory]):
    """CRUD plus lookups for :class:`DashboardHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardHistory, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardHistory]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardHistory.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_dashboard(
        self, dashboard_id: UUID, *, limit: int = 100
    ) -> list[DashboardHistory]:
        """Activity on one dashboard, most recent first."""
        stmt = (
            self._base_select()
            .where(DashboardHistory.dashboard_id == dashboard_id)
            .order_by(desc(DashboardHistory.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DashboardHistoryRepository"]
