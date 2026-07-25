"""Repository for :class:`app.models.discovery_statistics.DiscoveryStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_statistics import DiscoveryStatistics


class DiscoveryStatisticsRepository(BaseRepository[DiscoveryStatistics]):
    """CRUD plus lookup for :class:`DiscoveryStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> DiscoveryStatistics | None:
        """Return *organization_id*'s cached statistics snapshot, or ``None``."""
        stmt = self._base_select().where(DiscoveryStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["DiscoveryStatisticsRepository"]
