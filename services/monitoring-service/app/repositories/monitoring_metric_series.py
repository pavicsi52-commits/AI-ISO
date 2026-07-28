"""Repository for :class:`app.models.monitoring_metric_series.MonitoringMetricSeries`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_metric_series import MonitoringMetricSeries


class MonitoringMetricSeriesRepository(BaseRepository[MonitoringMetricSeries]):
    """CRUD plus lookup for :class:`MonitoringMetricSeries`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringMetricSeries, tenant_scope=tenant_scope)

    async def list_for_target(
        self,
        target_id: UUID,
        *,
        metric_id: UUID | None = None,
        since: datetime | None = None,
    ) -> list[MonitoringMetricSeries]:
        """Every data point for *target_id*, oldest first ("Historical Queries").

        Optionally narrowed to one *metric_id* and/or a time window
        starting at *since* ("Time-window Analysis").
        """
        stmt = self._base_select().where(MonitoringMetricSeries.target_id == target_id)
        if metric_id is not None:
            stmt = stmt.where(MonitoringMetricSeries.metric_id == metric_id)
        if since is not None:
            stmt = stmt.where(MonitoringMetricSeries.recorded_at >= since)
        stmt = stmt.order_by(MonitoringMetricSeries.recorded_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Delete every data point recorded before *cutoff* ("Retention Policies").

        Returns the number of rows deleted.
        """
        stmt = self._base_select().where(MonitoringMetricSeries.recorded_at < cutoff)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


__all__ = ["MonitoringMetricSeriesRepository"]
