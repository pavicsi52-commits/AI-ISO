"""Health-check result recording and rollup ("HEALTH MONITORING"
"Support": Heartbeat, Service Availability, Application Health,
Infrastructure Health, Dependency Health, Component Health, Cluster
Health, Overall Health Score).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.health_status import HealthStatus

from app.health.engine import compute_overall_status
from app.models.enums import HealthCheckType
from app.models.monitoring_health import MonitoringHealth
from app.repositories.monitoring_health import MonitoringHealthRepository


class MonitoringHealthService:
    """Records and reads target health-check results."""

    def __init__(self, health: MonitoringHealthRepository) -> None:
        self._health = health

    async def record(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        check_type: HealthCheckType,
        status: HealthStatus,
        message: str | None = None,
        checked_at: datetime | None = None,
    ) -> MonitoringHealth:
        """Record one health-check result snapshot."""
        return await self._health.create(
            MonitoringHealth(
                organization_id=organization_id,
                target_id=target_id,
                check_type=check_type,
                status=status,
                message=message,
                checked_at=checked_at or datetime.now(UTC),
            )
        )

    async def list_for_target(self, target_id: UUID) -> list[MonitoringHealth]:
        """Every health-check result recorded for *target_id*, most recent first."""
        return await self._health.list_for_target(target_id)

    async def get_latest_for_target(self, target_id: UUID) -> MonitoringHealth | None:
        """Return *target_id*'s own most recent health-check result, or ``None``."""
        return await self._health.get_latest_for_target(target_id)

    async def compute_overall_for_target(self, target_id: UUID) -> HealthStatus:
        """Roll up *target_id*'s own most recent result per
        :class:`~app.models.enums.HealthCheckType` into one overall status
        ("Overall Health Score").
        """
        results = await self._health.list_for_target(target_id)
        latest_by_type: dict[HealthCheckType, HealthStatus] = {}
        for result in results:
            if result.check_type not in latest_by_type:
                latest_by_type[result.check_type] = result.status
        return compute_overall_status(latest_by_type.values())


__all__ = ["MonitoringHealthService"]
