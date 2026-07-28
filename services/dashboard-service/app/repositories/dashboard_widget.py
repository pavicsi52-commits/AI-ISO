"""Repository for :class:`app.models.dashboard_widget.DashboardWidget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_widget import DashboardWidget


class DashboardWidgetRepository(BaseRepository[DashboardWidget]):
    """CRUD plus lookups for :class:`DashboardWidget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardWidget, tenant_scope=tenant_scope)

    async def list_for_dashboard(
        self, dashboard_id: UUID, *, enabled_only: bool = False
    ) -> list[DashboardWidget]:
        """Every widget on one dashboard, in display order."""
        stmt = self._base_select().where(DashboardWidget.dashboard_id == dashboard_id)
        if enabled_only:
            stmt = stmt.where(DashboardWidget.enabled.is_(True))
        stmt = stmt.order_by(DashboardWidget.display_order, DashboardWidget.widget_key)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[DashboardWidget]:
        """Every widget for an organization, for analytics rollups."""
        stmt = self._base_select().where(DashboardWidget.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, dashboard_id: UUID, widget_key: str) -> DashboardWidget | None:
        """Return one widget by its dashboard-scoped key."""
        stmt = self._base_select().where(
            DashboardWidget.dashboard_id == dashboard_id,
            DashboardWidget.widget_key == widget_key,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count_for_dashboard(self, dashboard_id: UUID) -> int:
        """How many widgets a dashboard has, counted in SQL.

        Used to enforce the per-dashboard ceiling. Loading every row to
        call ``len()`` would not survive a large installation.
        """
        stmt = (
            self._base_select()
            .with_only_columns(func.count(DashboardWidget.id))
            .where(DashboardWidget.dashboard_id == dashboard_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one_or_none() or 0)


__all__ = ["DashboardWidgetRepository"]
