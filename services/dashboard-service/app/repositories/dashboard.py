"""Repository for :class:`app.models.dashboard.Dashboard`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard
from app.models.enums import DashboardType, DashboardVisibility


class DashboardRepository(BaseRepository[Dashboard]):
    """CRUD plus lookups for :class:`Dashboard`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Dashboard, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        dashboard_type: DashboardType | None = None,
        enabled_only: bool = False,
    ) -> list[Dashboard]:
        """Dashboards for *organization_id*, optionally filtered."""
        stmt = self._base_select().where(Dashboard.organization_id == organization_id)
        if dashboard_type is not None:
            stmt = stmt.where(Dashboard.dashboard_type == dashboard_type)
        if enabled_only:
            stmt = stmt.where(Dashboard.enabled.is_(True))
        stmt = stmt.order_by(Dashboard.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_visible_to(self, organization_id: UUID, user_id: UUID) -> list[Dashboard]:
        """Dashboards this user can see without an explicit share.

        Covers only the *intrinsic* visibility rules: dashboards this
        user owns, plus everything published organization- or
        project-wide. Dashboards reachable through a
        :class:`~app.models.dashboard_share.DashboardShare` are resolved
        separately, because a share can be revoked or expired and that
        check does not belong in a static SQL predicate.
        """
        stmt = (
            self._base_select()
            .where(
                Dashboard.organization_id == organization_id,
                or_(
                    Dashboard.owner_id == user_id,
                    Dashboard.visibility.in_(
                        [DashboardVisibility.ORGANIZATION, DashboardVisibility.PROJECT]
                    ),
                ),
            )
            .order_by(Dashboard.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, organization_id: UUID, slug: str) -> Dashboard | None:
        """Return the dashboard registered under *slug*, if any."""
        stmt = self._base_select().where(
            Dashboard.organization_id == organization_id, Dashboard.slug == slug
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["DashboardRepository"]
