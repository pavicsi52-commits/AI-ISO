"""Reusable metric definition catalog CRUD."""

from __future__ import annotations

from uuid import UUID

from app.models.enums import MetricType
from app.models.monitoring_metric import MonitoringMetric
from app.repositories.monitoring_metric import MonitoringMetricRepository


class MonitoringMetricService:
    """Creates and reads reusable metric definitions."""

    def __init__(self, metrics: MonitoringMetricRepository) -> None:
        self._metrics = metrics

    async def get_by_id(self, metric_id: UUID) -> MonitoringMetric:
        """Return the metric identified by *metric_id*.

        Raises:
            NotFoundError: If no such metric exists.
        """
        return await self._metrics.require_by_id(metric_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringMetric]:
        """Every reusable metric definition for *organization_id*."""
        return await self._metrics.list_for_org(organization_id)

    async def list_for_collector(self, collector_id: UUID) -> list[MonitoringMetric]:
        """Every metric definition collected by *collector_id*."""
        return await self._metrics.list_for_collector(collector_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        collector_id: UUID | None,
        metric_type: MetricType,
        name: str,
        unit: str | None,
    ) -> MonitoringMetric:
        """Define a new reusable metric."""
        return await self._metrics.create(
            MonitoringMetric(
                organization_id=organization_id,
                collector_id=collector_id,
                metric_type=metric_type,
                name=name,
                unit=unit,
            )
        )

    async def get_or_create_by_name(
        self, *, organization_id: UUID, name: str, metric_type: MetricType, unit: str | None = None
    ) -> MonitoringMetric:
        """Reuse the metric already defined under *name* for *organization_id*,
        or define a new one.
        """
        existing = await self._metrics.get_by_name(organization_id, name)
        if existing is not None:
            return existing
        return await self.create(
            organization_id=organization_id,
            collector_id=None,
            metric_type=metric_type,
            name=name,
            unit=unit,
        )


__all__ = ["MonitoringMetricService"]
