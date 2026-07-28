"""Repository for :class:`app.models.dashboard_view.DashboardView`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_view import DashboardView


class DashboardViewRepository(BaseRepository[DashboardView]):
    """CRUD plus lookups for :class:`DashboardView`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardView, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, since: datetime | None = None, limit: int = 5_000
    ) -> list[DashboardView]:
        """Views for *organization_id*, most recent first.

        Bounded and optionally windowed: view rows accumulate quickly,
        and an analytics rollup should not have to load a year of them
        to answer "most viewed this week".
        """
        stmt = self._base_select().where(DashboardView.organization_id == organization_id)
        if since is not None:
            stmt = stmt.where(DashboardView.viewed_at >= since)
        stmt = stmt.order_by(desc(DashboardView.viewed_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_dashboard(
        self, dashboard_id: UUID, *, limit: int = 200
    ) -> list[DashboardView]:
        """Views of one dashboard, most recent first."""
        stmt = (
            self._base_select()
            .where(DashboardView.dashboard_id == dashboard_id)
            .order_by(desc(DashboardView.viewed_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DashboardViewRepository"]
