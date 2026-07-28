"""Retention/downsampling policy CRUD and enforcement ("TIME SERIES"
"Support": Retention Policies).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models.enums import AggregationFunction, MetricType
from app.models.monitoring_retention import MonitoringRetention
from app.repositories.monitoring_retention import MonitoringRetentionRepository
from app.services.metric_series import MonitoringMetricSeriesService
from app.timeseries.retention import resolve_retention_days


class MonitoringRetentionService:
    """Creates, reads, and enforces retention/downsampling policies."""

    def __init__(
        self,
        retention: MonitoringRetentionRepository,
        metric_series: MonitoringMetricSeriesService,
    ) -> None:
        self._retention = retention
        self._metric_series = metric_series

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringRetention]:
        """Every retention policy belonging to *organization_id*."""
        return await self._retention.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        metric_type: MetricType | None,
        retention_days: int,
        downsampling_function: AggregationFunction | None,
        downsampling_interval_seconds: float | None,
        is_active: bool,
    ) -> MonitoringRetention:
        """Configure a new retention/downsampling policy."""
        return await self._retention.create(
            MonitoringRetention(
                organization_id=organization_id,
                metric_type=metric_type,
                retention_days=retention_days,
                downsampling_function=downsampling_function,
                downsampling_interval_seconds=downsampling_interval_seconds,
                is_active=is_active,
            )
        )

    async def enforce_for_org(self, organization_id: UUID, metric_type: MetricType) -> int:
        """Delete every *metric_type* data point older than the applicable
        retention window for *organization_id*.

        Returns the number of rows deleted.
        """
        policies = await self._retention.list_for_org(organization_id)
        retention_days = resolve_retention_days(policies, metric_type)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        return await self._metric_series.delete_older_than(cutoff)


__all__ = ["MonitoringRetentionService"]
