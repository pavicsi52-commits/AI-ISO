"""Report generation. Per docs/044 "REPORTING" "Generate": Health
Reports, Availability Reports, Performance Reports, Capacity Reports,
Executive Dashboards, SLA Reports, SLO Reports, Historical Reports.
Matches the "GET-as-generate" precedent
``services/validation-service``'s own ``ValidationReportService``
already established: a report is computed and persisted the moment
it's requested, not queued for later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.health.engine import score_from_status
from app.models.enums import MonitoringReportType
from app.models.monitoring_report import MonitoringReport
from app.repositories.monitoring_report import MonitoringReportRepository
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService
from app.services.history import MonitoringHistoryService
from app.services.performance import MonitoringPerformanceService
from app.services.statistics import MonitoringStatisticsService

_TARGET_SCOPED_REPORT_TYPES = frozenset(
    {
        MonitoringReportType.HEALTH,
        MonitoringReportType.AVAILABILITY,
        MonitoringReportType.PERFORMANCE,
        MonitoringReportType.HISTORICAL,
    }
)


class MonitoringReportService:
    """Generates and lists monitoring reports."""

    def __init__(
        self,
        reports: MonitoringReportRepository,
        health: MonitoringHealthService,
        availability: MonitoringAvailabilityService,
        performance: MonitoringPerformanceService,
        history: MonitoringHistoryService,
        statistics: MonitoringStatisticsService,
        slas: MonitoringSLARepository,
        slos: MonitoringSLORepository,
    ) -> None:
        self._reports = reports
        self._health = health
        self._availability = availability
        self._performance = performance
        self._history = history
        self._statistics = statistics
        self._slas = slas
        self._slos = slos

    async def list_for_org(
        self, organization_id: UUID, *, report_type: MonitoringReportType | None = None
    ) -> list[MonitoringReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def _health_report(self, target_id: UUID) -> dict[str, Any]:
        status = await self._health.compute_overall_for_target(target_id)
        return {"overall_status": str(status), "health_score": score_from_status(status)}

    async def _availability_report(self, target_id: UUID) -> dict[str, Any]:
        intervals = await self._availability.list_for_target(target_id)
        closed = [i for i in intervals if i.duration_seconds is not None]
        return {
            "interval_count": len(intervals),
            "total_downtime_seconds": sum(
                i.duration_seconds or 0.0 for i in closed if str(i.status) != "up"
            ),
        }

    async def _performance_report(self, target_id: UUID) -> dict[str, Any]:
        return {"metrics": await self._performance.summarize_for_target(target_id)}

    async def _historical_report(self, target_id: UUID) -> dict[str, Any]:
        records = await self._history.list_for_target(target_id)
        return {"total_snapshots": len(records), "scores": [r.score for r in records]}

    async def _capacity_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {"total_targets": snapshot.total_targets, "trend_data": snapshot.trend_data}

    async def _executive_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_targets": snapshot.total_targets,
            "average_health_score": snapshot.average_health_score,
            "average_availability_percentage": snapshot.average_availability_percentage,
            "sla_compliance_percentage": snapshot.sla_compliance_percentage,
            "slo_compliance_percentage": snapshot.slo_compliance_percentage,
        }

    async def _sla_report(self, organization_id: UUID) -> dict[str, Any]:
        slas = await self._slas.list_for_org(organization_id)
        return {
            "total_slas": len(slas),
            "violated_count": sum(1 for s in slas if str(s.status) == "violated"),
        }

    async def _slo_report(self, organization_id: UUID) -> dict[str, Any]:
        slos = await self._slos.list_for_org(organization_id)
        return {
            "total_slos": len(slos),
            "violated_count": sum(1 for s in slos if str(s.status) == "violated"),
        }

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: MonitoringReportType,
        target_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> MonitoringReport:
        """Generate and persist a report ("Generate").

        Raises:
            ValidationError: If *report_type* is target-scoped but no
                *target_id* was given.
        """
        if report_type in _TARGET_SCOPED_REPORT_TYPES:
            if target_id is None:
                raise ValidationError(f"Report type {report_type!r} requires a target_id.")
            if report_type is MonitoringReportType.HEALTH:
                result = await self._health_report(target_id)
            elif report_type is MonitoringReportType.AVAILABILITY:
                result = await self._availability_report(target_id)
            elif report_type is MonitoringReportType.PERFORMANCE:
                result = await self._performance_report(target_id)
            else:
                result = await self._historical_report(target_id)
        elif report_type is MonitoringReportType.CAPACITY:
            result = await self._capacity_report(organization_id)
        elif report_type is MonitoringReportType.EXECUTIVE:
            result = await self._executive_report(organization_id)
        elif report_type is MonitoringReportType.SLA:
            result = await self._sla_report(organization_id)
        else:
            result = await self._slo_report(organization_id)

        return await self._reports.create(
            MonitoringReport(
                organization_id=organization_id,
                target_id=target_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["MonitoringReportService"]
