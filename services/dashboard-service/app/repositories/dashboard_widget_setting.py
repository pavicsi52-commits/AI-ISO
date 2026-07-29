"""Repository for :class:`app.models.dashboard_widget_setting.DashboardWidgetSetting`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_widget_setting import DashboardWidgetSetting


class DashboardWidgetSettingRepository(BaseRepository[DashboardWidgetSetting]):
    """CRUD plus lookups for :class:`DashboardWidgetSetting`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardWidgetSetting, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardWidgetSetting]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardWidgetSetting.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user(self, widget_id: UUID, user_id: UUID) -> DashboardWidgetSetting | None:
        """One user's overrides for one widget, if they have any."""
        stmt = self._base_select().where(
            DashboardWidgetSetting.widget_id == widget_id,
            DashboardWidgetSetting.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_user(
        self, organization_id: UUID, user_id: UUID
    ) -> list[DashboardWidgetSetting]:
        """Every override one user has, for applying in bulk on load."""
        stmt = self._base_select().where(
            DashboardWidgetSetting.organization_id == organization_id,
            DashboardWidgetSetting.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DashboardWidgetSettingRepository"]
