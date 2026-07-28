"""Repository for :class:`app.models.monitoring_metric.MonitoringMetric`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_metric import MonitoringMetric


class MonitoringMetricRepository(BaseRepository[MonitoringMetric]):
    """CRUD plus lookup for :class:`MonitoringMetric`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringMetric, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringMetric]:
        """Every reusable metric definition for *organization_id*."""
        stmt = self._base_select().where(MonitoringMetric.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_collector(self, collector_id: UUID) -> list[MonitoringMetric]:
        """Every metric definition collected by *collector_id*."""
        stmt = self._base_select().where(MonitoringMetric.collector_id == collector_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, organization_id: UUID, name: str) -> MonitoringMetric | None:
        """Return the metric already defined under *name* for *organization_id*, if any."""
        stmt = self._base_select().where(
            MonitoringMetric.organization_id == organization_id, MonitoringMetric.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["MonitoringMetricRepository"]
