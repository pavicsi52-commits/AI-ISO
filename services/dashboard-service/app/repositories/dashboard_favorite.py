"""Repository for :class:`app.models.dashboard_favorite.DashboardFavorite`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_favorite import DashboardFavorite


class DashboardFavoriteRepository(BaseRepository[DashboardFavorite]):
    """CRUD plus lookups for :class:`DashboardFavorite`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardFavorite, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardFavorite]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardFavorite.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, organization_id: UUID, user_id: UUID) -> list[DashboardFavorite]:
        """Every dashboard one user has pinned, in their own order."""
        stmt = (
            self._base_select()
            .where(
                DashboardFavorite.organization_id == organization_id,
                DashboardFavorite.user_id == user_id,
            )
            .order_by(DashboardFavorite.display_order)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user_dashboard(
        self, user_id: UUID, dashboard_id: UUID
    ) -> DashboardFavorite | None:
        """One user's favourite of one dashboard, if it exists."""
        stmt = self._base_select().where(
            DashboardFavorite.user_id == user_id,
            DashboardFavorite.dashboard_id == dashboard_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["DashboardFavoriteRepository"]
