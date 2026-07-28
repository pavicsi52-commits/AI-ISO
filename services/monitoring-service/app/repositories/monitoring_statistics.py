"""Repository for :class:`app.models.monitoring_statistics.MonitoringStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_statistics import MonitoringStatistics


class MonitoringStatisticsRepository(BaseRepository[MonitoringStatistics]):
    """CRUD plus lookup for :class:`MonitoringStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> MonitoringStatistics | None:
        """Return *organization_id*'s cached analytics snapshot, or ``None``."""
        stmt = self._base_select().where(MonitoringStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["MonitoringStatisticsRepository"]
