"""Report generation. Per docs/039 "REPORTING" "Generate": Configuration,
Compliance, Drift, Baseline, Version, Approval Reports, Executive
Dashboards.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.configuration_report import ConfigurationReport
from app.models.enums import ConfigReportType
from app.repositories.configuration_report import ConfigurationReportRepository
from app.services.approval import ConfigurationApprovalService
from app.services.baseline import ConfigurationBaselineService
from app.services.compliance import ConfigurationComplianceService
from app.services.drift import ConfigurationDriftService
from app.services.profile import ConfigurationProfileService
from app.services.statistics import ConfigurationStatisticsService
from app.services.version import ConfigurationVersionService


class ConfigurationReportService:
    """Generates and lists configuration-management reports."""

    def __init__(
        self,
        reports: ConfigurationReportRepository,
        profiles: ConfigurationProfileService,
        compliance: ConfigurationComplianceService,
        drift: ConfigurationDriftService,
        baselines: ConfigurationBaselineService,
        versions: ConfigurationVersionService,
        approvals: ConfigurationApprovalService,
        statistics: ConfigurationStatisticsService,
    ) -> None:
        self._reports = reports
        self._profiles = profiles
        self._compliance = compliance
        self._drift = drift
        self._baselines = baselines
        self._versions = versions
        self._approvals = approvals
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ConfigReportType | None = None
    ) -> list[ConfigurationReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationReport]:
        """Every generated report scoped to *profile_id*."""
        return await self._reports.list_for_profile(profile_id)

    async def _configuration_report(self, profile_id: UUID) -> dict[str, Any]:
        profile = await self._profiles.get_by_id(profile_id)
        return {
            "profile_name": profile.profile_name,
            "status": str(profile.status),
            "profile_version": profile.profile_version,
            "configuration_type": str(profile.configuration_type),
            "target_asset_count": len(profile.target_assets),
        }

    async def _compliance_report(self, profile_id: UUID) -> dict[str, Any]:
        entries = await self._compliance.list_for_profile(profile_id)
        return {
            "total_evaluations": len(entries),
            "by_status": {
                str(status): sum(1 for e in entries if e.status == status)
                for status in {e.status for e in entries}
            },
        }

    async def _drift_report(self, profile_id: UUID) -> dict[str, Any]:
        entries = await self._drift.list_for_profile(profile_id)
        return {
            "total_drift_instances": len(entries),
            "by_type": {
                str(drift_type): sum(1 for e in entries if e.drift_type == drift_type)
                for drift_type in {e.drift_type for e in entries}
            },
        }

    async def _baseline_report(self, profile_id: UUID) -> dict[str, Any]:
        entries = await self._baselines.list_for_profile(profile_id)
        return {
            "total_baselines": len(entries),
            "baseline_types": sorted({str(entry.baseline_type) for entry in entries}),
        }

    async def _version_report(self, profile_id: UUID) -> dict[str, Any]:
        entries = await self._versions.list_for_profile(profile_id)
        return {
            "total_versions": len(entries),
            "latest_version_number": entries[0].version_number if entries else None,
        }

    async def _approval_report(self, profile_id: UUID) -> dict[str, Any]:
        entries = await self._approvals.list_for_profile(profile_id)
        return {
            "total_approvals": len(entries),
            "by_status": {
                str(status): sum(1 for e in entries if e.status == status)
                for status in {e.status for e in entries}
            },
        }

    async def _executive_dashboard_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_profiles": snapshot.total_profiles,
            "total_versions": snapshot.total_versions,
            "drift_statistics": snapshot.drift_statistics,
            "compliance_scores": snapshot.compliance_scores,
            "deployment_readiness": snapshot.deployment_readiness,
        }

    async def _build_result(
        self, organization_id: UUID, *, report_type: ConfigReportType, profile_id: UUID | None
    ) -> dict[str, Any]:
        if report_type is ConfigReportType.EXECUTIVE_DASHBOARD:
            return await self._executive_dashboard_report(organization_id)
        if profile_id is None:
            raise ValidationError(f"Report type {report_type!r} requires a profile_id.")

        builders: dict[ConfigReportType, Callable[[UUID], Awaitable[dict[str, Any]]]] = {
            ConfigReportType.CONFIGURATION: self._configuration_report,
            ConfigReportType.COMPLIANCE: self._compliance_report,
            ConfigReportType.DRIFT: self._drift_report,
            ConfigReportType.BASELINE: self._baseline_report,
            ConfigReportType.VERSION: self._version_report,
            ConfigReportType.APPROVAL: self._approval_report,
        }
        return await builders[report_type](profile_id)

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: ConfigReportType,
        profile_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> ConfigurationReport:
        """Generate and persist a report ("Generate")."""
        result = await self._build_result(
            organization_id, report_type=report_type, profile_id=profile_id
        )
        return await self._reports.create(
            ConfigurationReport(
                organization_id=organization_id,
                profile_id=profile_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["ConfigurationReportService"]
