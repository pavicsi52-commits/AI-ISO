"""Threshold configuration CRUD ("THRESHOLDS" "Support")."""

from __future__ import annotations

from uuid import UUID

from app.models.enums import ThresholdType
from app.models.monitoring_threshold import MonitoringThreshold
from app.repositories.monitoring_threshold import MonitoringThresholdRepository


class MonitoringThresholdService:
    """Creates and reads threshold configurations."""

    def __init__(self, thresholds: MonitoringThresholdRepository) -> None:
        self._thresholds = thresholds

    async def get_by_id(self, threshold_id: UUID) -> MonitoringThreshold:
        """Return the threshold identified by *threshold_id*.

        Raises:
            NotFoundError: If no such threshold exists.
        """
        return await self._thresholds.require_by_id(threshold_id)

    async def list_for_metric(self, metric_id: UUID) -> list[MonitoringThreshold]:
        """Every active threshold configured for *metric_id*."""
        return await self._thresholds.list_for_metric(metric_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        metric_id: UUID,
        threshold_type: ThresholdType,
        informational: float | None,
        low: float | None,
        medium: float | None,
        high: float | None,
        critical: float | None,
        is_active: bool,
    ) -> MonitoringThreshold:
        """Configure a new threshold."""
        return await self._thresholds.create(
            MonitoringThreshold(
                organization_id=organization_id,
                metric_id=metric_id,
                threshold_type=threshold_type,
                informational=informational,
                low=low,
                medium=medium,
                high=high,
                critical=critical,
                is_active=is_active,
            )
        )


__all__ = ["MonitoringThresholdService"]
