"""Repository for :class:`app.models.monitoring_collector.MonitoringCollector`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_collector import MonitoringCollector


class MonitoringCollectorRepository(BaseRepository[MonitoringCollector]):
    """CRUD plus lookup for :class:`MonitoringCollector`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringCollector, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringCollector]:
        """Every collector configuration belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringCollector.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_active(self) -> list[MonitoringCollector]:
        """Every active collector, system-wide (for scheduling)."""
        stmt = self._base_select().where(MonitoringCollector.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringCollectorRepository"]
