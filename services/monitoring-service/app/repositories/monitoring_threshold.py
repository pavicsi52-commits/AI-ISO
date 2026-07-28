"""Repository for :class:`app.models.monitoring_threshold.MonitoringThreshold`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_threshold import MonitoringThreshold


class MonitoringThresholdRepository(BaseRepository[MonitoringThreshold]):
    """CRUD plus lookup for :class:`MonitoringThreshold`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringThreshold, tenant_scope=tenant_scope)

    async def list_for_metric(self, metric_id: UUID) -> list[MonitoringThreshold]:
        """Every active threshold configured for *metric_id*."""
        stmt = self._base_select().where(
            MonitoringThreshold.metric_id == metric_id,
            MonitoringThreshold.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringThresholdRepository"]
