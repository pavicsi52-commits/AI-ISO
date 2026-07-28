"""Report generation. Per docs/045 "REPORTING" "Generate": Alert
Reports, Executive Reports, Operational Reports, SLA Reports,
Escalation Reports, Trend Reports, Noise Analysis. Matches the
"GET-as-generate" precedent every prior AI-IOS service's own report
service established: a report is computed and persisted the moment
it's requested, not queued for later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.alert_report import AlertReport
from app.models.enums import AlertReportType
from app.repositories.alert_report import AlertReportRepository
from app.services.alert import AlertService
from app.services.statistics import AlertStatisticsService


class AlertReportService:
    """Generates and lists alerting reports."""

    def __init__(
        self,
        reports: AlertReportRepository,
        alerts: AlertService,
        statistics: AlertStatisticsService,
    ) -> None:
        self._reports = reports
        self._alerts = alerts
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: AlertReportType | None = None
    ) -> list[AlertReport]:
        """Every generated report for *organization_id*."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def _alert_report(self, alert_id: UUID) -> dict[str, Any]:
        alert = await self._alerts.get_by_id(alert_id)
        history = await self._alerts.list_history(alert_id)
        return {
            "status": str(alert.status),
            "severity": str(alert.severity),
            "source": str(alert.source),
            "triggered_at": alert.triggered_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "transition_count": len(history),
        }

    async def _executive_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_alerts": snapshot.total_alerts,
            "open_alert_count": snapshot.open_alert_count,
            "mtta_seconds": snapshot.mtta_seconds,
            "mttr_seconds": snapshot.mttr_seconds,
        }

    async def _operational_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_alerts": snapshot.total_alerts,
            "average_resolution_seconds": snapshot.average_resolution_seconds,
            "top_sources": snapshot.top_sources,
            "top_rules": snapshot.top_rules,
        }

    async def _sla_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "mtta_seconds": snapshot.mtta_seconds,
            "mttr_seconds": snapshot.mttr_seconds,
            "average_resolution_seconds": snapshot.average_resolution_seconds,
        }

    async def _escalation_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {"escalation_statistics": snapshot.escalation_statistics}

    async def _trend_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {"trend_data": snapshot.trend_data}

    async def _noise_analysis_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "noise_ratio": snapshot.noise_ratio,
            "suppression_rate": snapshot.suppression_rate,
            "top_rules": snapshot.top_rules,
        }

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: AlertReportType,
        alert_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> AlertReport:
        """Generate and persist a report.

        Raises:
            ValidationError: If an ``ALERT`` report is requested with no *alert_id*.
        """
        if report_type is AlertReportType.ALERT:
            if alert_id is None:
                raise ValidationError("An alert report requires an alert_id.")
            result = await self._alert_report(alert_id)
        elif report_type is AlertReportType.EXECUTIVE:
            result = await self._executive_report(organization_id)
        elif report_type is AlertReportType.OPERATIONAL:
            result = await self._operational_report(organization_id)
        elif report_type is AlertReportType.SLA:
            result = await self._sla_report(organization_id)
        elif report_type is AlertReportType.ESCALATION:
            result = await self._escalation_report(organization_id)
        elif report_type is AlertReportType.TREND:
            result = await self._trend_report(organization_id)
        else:
            result = await self._noise_analysis_report(organization_id)

        return await self._reports.create(
            AlertReport(
                organization_id=organization_id,
                alert_id=alert_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["AlertReportService"]
