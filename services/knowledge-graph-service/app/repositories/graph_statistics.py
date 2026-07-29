"""Repository for :class:`app.models.graph_statistics.GraphStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_statistics import GraphStatistics


class GraphStatisticsRepository(BaseRepository[GraphStatistics]):
    """CRUD plus lookups for :class:`GraphStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphStatistics, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[GraphStatistics]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(GraphStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_org(self, organization_id: UUID) -> GraphStatistics | None:
        """Return the cached rollup for *organization_id*, or ``None``."""
        stmt = self._base_select().where(GraphStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["GraphStatisticsRepository"]
