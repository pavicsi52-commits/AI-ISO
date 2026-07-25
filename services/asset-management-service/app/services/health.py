"""Health rollup aggregation. Per docs/038 "HEALTH MANAGEMENT"
"Aggregate": Monitoring Status, Validation Status, Discovery Status,
Automation Status, Incident Count, Performance Indicators,
Availability, Health Score, Health Trends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.asset_health_rollup import AssetHealthRollup
from app.models.enums import OperationalHealth
from app.repositories.asset_health_rollup import AssetHealthRollupRepository
from app.repositories.managed_asset import ManagedAssetRepository

_TREND_HISTORY_LIMIT = 30
_WARNING_THRESHOLD = 70.0
_CRITICAL_THRESHOLD = 40.0


def _derive_operational_health(health_score: float) -> OperationalHealth:
    if health_score < _CRITICAL_THRESHOLD:
        return OperationalHealth.CRITICAL
    if health_score < _WARNING_THRESHOLD:
        return OperationalHealth.WARNING
    return OperationalHealth.HEALTHY


class HealthService:
    """Recomputes and reads a managed asset's cached health rollup."""

    def __init__(
        self, rollups: AssetHealthRollupRepository, managed_assets: ManagedAssetRepository
    ) -> None:
        self._rollups = rollups
        self._managed_assets = managed_assets

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetHealthRollup | None:
        """Return *managed_asset_id*'s cached health rollup, or ``None``."""
        return await self._rollups.get_for_managed_asset(managed_asset_id)

    async def recompute(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        monitoring_status: str,
        validation_status: str,
        discovery_status: str,
        automation_status: str,
        incident_count: int,
        performance_indicators: dict[str, Any],
        availability_percent: float | None,
        health_score: float,
    ) -> AssetHealthRollup:
        """Recompute *managed_asset_id*'s health rollup ("Aggregate"),
        appending to its rolling ``health_trend`` and updating the
        managed asset's denormalized ``operational_health`` summary.
        """
        now = datetime.now(UTC)
        trend_point = {"health_score": health_score, "computed_at": now.isoformat()}

        existing = await self.get_for_managed_asset(managed_asset_id)
        if existing is not None:
            existing.monitoring_status = monitoring_status
            existing.validation_status = validation_status
            existing.discovery_status = discovery_status
            existing.automation_status = automation_status
            existing.incident_count = incident_count
            existing.performance_indicators = performance_indicators
            existing.availability_percent = availability_percent
            existing.health_score = health_score
            existing.health_trend = [*existing.health_trend, trend_point][-_TREND_HISTORY_LIMIT:]
            existing.computed_at = now
            rollup = existing
        else:
            rollup = await self._rollups.create(
                AssetHealthRollup(
                    managed_asset_id=managed_asset_id,
                    organization_id=organization_id,
                    monitoring_status=monitoring_status,
                    validation_status=validation_status,
                    discovery_status=discovery_status,
                    automation_status=automation_status,
                    incident_count=incident_count,
                    performance_indicators=performance_indicators,
                    availability_percent=availability_percent,
                    health_score=health_score,
                    health_trend=[trend_point],
                    computed_at=now,
                )
            )

        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        managed_asset.operational_health = _derive_operational_health(health_score)
        return rollup


__all__ = ["HealthService"]
