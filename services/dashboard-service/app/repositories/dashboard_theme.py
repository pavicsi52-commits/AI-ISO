"""Repository for :class:`app.models.dashboard_theme.DashboardTheme`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_theme import DashboardTheme


class DashboardThemeRepository(BaseRepository[DashboardTheme]):
    """CRUD plus lookups for :class:`DashboardTheme`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardTheme, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DashboardTheme]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(DashboardTheme.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, organization_id: UUID, slug: str) -> DashboardTheme | None:
        """Return the theme registered under *slug*, if any."""
        stmt = self._base_select().where(
            DashboardTheme.organization_id == organization_id, DashboardTheme.slug == slug
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["DashboardThemeRepository"]
