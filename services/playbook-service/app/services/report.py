"""Report generation. Per docs/041 "REPORTING" "Generate": Repository
Reports, Validation Reports, Approval Reports, Version Reports,
Dependency Reports, Executive Dashboards. Matches the "GET-as-generate"
precedent ``services/configuration-management-service``'s own
``ConfigurationReportService`` established: a report is computed and
persisted the moment it's requested, not queued for later.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import PlaybookReportType
from app.models.playbook_report import PlaybookReport
from app.repositories.playbook_report import PlaybookReportRepository
from app.services.approval import PlaybookApprovalService
from app.services.dependency import PlaybookDependencyService
from app.services.playbook import PlaybookService
from app.services.statistics import PlaybookStatisticsService
from app.services.version import PlaybookVersionService
from app.validators.content_validator import validate_content


class PlaybookReportService:
    """Generates and lists playbook-repository reports."""

    def __init__(
        self,
        reports: PlaybookReportRepository,
        playbooks: PlaybookService,
        versions: PlaybookVersionService,
        dependencies: PlaybookDependencyService,
        approvals: PlaybookApprovalService,
        statistics: PlaybookStatisticsService,
    ) -> None:
        self._reports = reports
        self._playbooks = playbooks
        self._versions = versions
        self._dependencies = dependencies
        self._approvals = approvals
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: PlaybookReportType | None = None
    ) -> list[PlaybookReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookReport]:
        """Every generated report scoped to *playbook_id*."""
        return await self._reports.list_for_playbook(playbook_id)

    async def _repository_report(self, organization_id: UUID) -> dict[str, Any]:
        playbooks = await self._playbooks.list_for_org(organization_id)
        return {
            "total_playbooks": len(playbooks),
            "by_status": {
                str(status): sum(1 for p in playbooks if p.status == status)
                for status in {p.status for p in playbooks}
            },
        }

    async def _validation_report(self, playbook_id: UUID) -> dict[str, Any]:
        playbook = await self._playbooks.get_by_id(playbook_id)
        latest = await self._versions.get_latest_for_playbook(playbook_id)
        if latest is None:
            return {"has_content": False, "errors": []}
        errors = await validate_content(playbook.content_type, latest.content)
        return {"has_content": True, "valid": not errors, "errors": errors}

    async def _approval_report(self, playbook_id: UUID) -> dict[str, Any]:
        entries = await self._approvals.list_for_playbook(playbook_id)
        return {
            "total_approvals": len(entries),
            "by_status": {
                str(status): sum(1 for e in entries if e.status == status)
                for status in {e.status for e in entries}
            },
        }

    async def _version_report(self, playbook_id: UUID) -> dict[str, Any]:
        entries = await self._versions.list_for_playbook(playbook_id)
        return {
            "total_versions": len(entries),
            "latest_version_number": entries[0].version_number if entries else None,
        }

    async def _dependency_report(self, playbook_id: UUID) -> dict[str, Any]:
        entries = await self._dependencies.list_for_playbook(playbook_id)
        counts = Counter(str(entry.dependency_type) for entry in entries)
        return {"total_dependencies": len(entries), "by_type": dict(counts)}

    async def _executive_dashboard_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_playbooks": snapshot.total_playbooks,
            "total_versions": snapshot.total_versions,
            "approvals_summary": snapshot.approvals_summary,
            "validation_results_summary": snapshot.validation_results_summary,
            "deprecated_content_count": snapshot.deprecated_content_count,
        }

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: PlaybookReportType,
        playbook_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> PlaybookReport:
        """Generate and persist a report ("Generate").

        Raises:
            ValidationError: If *report_type* requires a *playbook_id*
                that wasn't given.
        """
        if report_type is PlaybookReportType.REPOSITORY:
            result = await self._repository_report(organization_id)
        elif report_type is PlaybookReportType.EXECUTIVE_DASHBOARD:
            result = await self._executive_dashboard_report(organization_id)
        elif playbook_id is None:
            raise ValidationError(f"Report type {report_type!r} requires a playbook_id.")
        elif report_type is PlaybookReportType.VALIDATION:
            result = await self._validation_report(playbook_id)
        elif report_type is PlaybookReportType.APPROVAL:
            result = await self._approval_report(playbook_id)
        elif report_type is PlaybookReportType.VERSION:
            result = await self._version_report(playbook_id)
        else:
            result = await self._dependency_report(playbook_id)

        return await self._reports.create(
            PlaybookReport(
                organization_id=organization_id,
                playbook_id=playbook_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["PlaybookReportService"]
