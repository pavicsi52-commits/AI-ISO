"""Time-series metric data point recording and querying ("High-frequency
Metrics", "Historical Queries", "Time-window Analysis").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.monitoring_metric_series import MonitoringMetricSeries
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository


class MonitoringMetricSeriesService:
    """Records and reads time-series metric data points."""

    def __init__(self, series: MonitoringMetricSeriesRepository) -> None:
        self._series = series

    async def record(
        self,
        *,
        organization_id: UUID,
        metric_id: UUID,
        target_id: UUID,
        value: float,
        tags: dict[str, Any] | None = None,
        recorded_at: datetime | None = None,
    ) -> MonitoringMetricSeries:
        """Record one measured data point."""
        return await self._series.create(
            MonitoringMetricSeries(
                organization_id=organization_id,
                metric_id=metric_id,
                target_id=target_id,
                value=value,
                tags=tags or {},
                recorded_at=recorded_at or datetime.now(UTC),
            )
        )

    async def list_for_target(
        self, target_id: UUID, *, metric_id: UUID | None = None, since: datetime | None = None
    ) -> list[MonitoringMetricSeries]:
        """Every data point for *target_id*, oldest first."""
        return await self._series.list_for_target(target_id, metric_id=metric_id, since=since)

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Enforce a retention cutoff, deleting every data point recorded before it."""
        return await self._series.delete_older_than(cutoff)


__all__ = ["MonitoringMetricSeriesService"]
