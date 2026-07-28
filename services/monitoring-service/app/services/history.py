"""Per-target lightweight historical health trend snapshots ("Availability
Trends"/"Failure Trends").
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.health_status import HealthStatus

from app.models.monitoring_history import MonitoringHistory
from app.repositories.monitoring_history import MonitoringHistoryRepository


class MonitoringHistoryService:
    """Records and reads per-target historical health snapshots."""

    def __init__(self, history: MonitoringHistoryRepository) -> None:
        self._history = history

    async def list_for_target(self, target_id: UUID) -> list[MonitoringHistory]:
        """Every historical snapshot for *target_id*, oldest first."""
        return await self._history.list_for_target(target_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringHistory]:
        """Every historical snapshot for *organization_id*, oldest first."""
        return await self._history.list_for_org(organization_id)

    async def record(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        status: HealthStatus,
        score: float | None,
        recorded_at: datetime | None = None,
    ) -> MonitoringHistory:
        """Record one historical snapshot for a target."""
        return await self._history.create(
            MonitoringHistory(
                organization_id=organization_id,
                target_id=target_id,
                status=status,
                score=score,
                recorded_at=recorded_at or datetime.now(UTC),
            )
        )


__all__ = ["MonitoringHistoryService"]
