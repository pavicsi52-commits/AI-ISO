"""Organization-wide monitoring analytics computation. Per docs/044
"ANALYTICS" "Collect": Metric Trends, Capacity Trends, Availability
Trends, Failure Trends, Resource Utilization, Growth Analysis,
Forecasting Inputs. Computed on demand and cached, the same "cached,
not live" shape ``services/validation-service``'s own
``ValidationStatisticsService`` already established.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from app.health.engine import score_from_status
from app.models.enums import AvailabilityStatus, ComplianceStatus
from app.models.monitoring_statistics import MonitoringStatistics
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.repositories.monitoring_statistics import MonitoringStatisticsRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService


class MonitoringStatisticsService:
    """Recomputes and reads an organization's cached monitoring analytics."""

    def __init__(
        self,
        statistics: MonitoringStatisticsRepository,
        targets: MonitoringTargetRepository,
        health: MonitoringHealthService,
        availability: MonitoringAvailabilityService,
        slas: MonitoringSLARepository,
        slos: MonitoringSLORepository,
    ) -> None:
        self._statistics = statistics
        self._targets = targets
        self._health = health
        self._availability = availability
        self._slas = slas
        self._slos = slos

    async def get_for_org(self, organization_id: UUID) -> MonitoringStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> MonitoringStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        targets = await self._targets.list_for_org(organization_id)

        health_scores = [
            score_from_status(await self._health.compute_overall_for_target(target.id))
            for target in targets
        ]
        average_health_score = sum(health_scores) / len(health_scores) if health_scores else 0.0

        availability_percentages: list[float] = []
        trend_data: dict[str, list[float]] = defaultdict(list)
        for target in targets:
            intervals = await self._availability.list_for_target(target.id)
            closed = [interval for interval in intervals if interval.duration_seconds is not None]
            total_seconds = sum(interval.duration_seconds or 0.0 for interval in closed)
            if total_seconds > 0:
                up_seconds = sum(
                    interval.duration_seconds or 0.0
                    for interval in closed
                    if interval.status == AvailabilityStatus.UP
                )
                availability_percentages.append((up_seconds / total_seconds) * 100)
            for interval in intervals:
                trend_data[str(target.id)].append(
                    100.0 if interval.status == AvailabilityStatus.UP else 0.0
                )
        average_availability_percentage = (
            sum(availability_percentages) / len(availability_percentages)
            if availability_percentages
            else 100.0
        )

        slas = await self._slas.list_for_org(organization_id)
        sla_compliance_percentage = _compliance_percentage(sla.status for sla in slas)
        slos = await self._slos.list_for_org(organization_id)
        slo_compliance_percentage = _compliance_percentage(slo.status for slo in slos)

        snapshot_fields = {
            "total_targets": len(targets),
            "total_metrics_collected": 0,
            "average_availability_percentage": average_availability_percentage,
            "average_health_score": average_health_score,
            "sla_compliance_percentage": sla_compliance_percentage,
            "slo_compliance_percentage": slo_compliance_percentage,
            "top_threshold_breaches": {},
            "trend_data": dict(trend_data),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            MonitoringStatistics(organization_id=organization_id, **snapshot_fields)
        )


def _compliance_percentage(statuses: Iterable[ComplianceStatus]) -> float:
    resolved = list(statuses)
    if not resolved:
        return 100.0
    compliant = sum(1 for status in resolved if status == ComplianceStatus.COMPLIANT)
    return (compliant / len(resolved)) * 100


__all__ = ["MonitoringStatisticsService"]
