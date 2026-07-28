"""Repository for :class:`app.models.dashboard_filter.DashboardFilter`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_filter import DashboardFilter


class DashboardFilterRepository(BaseRepository[DashboardFilter]):
    """CRUD plus lookups for :class:`DashboardFilter`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardFilter, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardFilter]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardFilter.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_dashboard(
        self, dashboard_id: UUID, *, user_id: UUID | None = None
    ) -> list[DashboardFilter]:
        """Saved filters for a dashboard.

        With *user_id*, returns that person's own saved filters plus the
        shared presets (those with no owner) -- which is what a filter
        picker should show.
        """
        stmt = self._base_select().where(DashboardFilter.dashboard_id == dashboard_id)
        if user_id is not None:
            stmt = stmt.where(
                or_(
                    DashboardFilter.user_id == user_id,
                    DashboardFilter.user_id.is_(None),
                )
            )
        stmt = stmt.order_by(DashboardFilter.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DashboardFilterRepository"]
