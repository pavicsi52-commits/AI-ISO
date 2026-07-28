"""Reporting analytics ("ANALYTICS").

Collects everything docs/047 names: generated reports, execution time,
popular reports, export types, template usage, schedule usage, download
count, and distribution statistics.

One row per organization, updated in place. A time series of snapshots
would be a different (and much larger) design; the per-run history any
trend would need already lives in ``report_executions``.

Every read is sequential. An ``AsyncSession`` is not safe for
concurrent use even for reads, so gathering these queries would trade a
few milliseconds for corruption.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import DistributionStatus, ReportExecutionStatus
from app.models.report_statistics import ReportStatistics
from app.repositories.report_distribution import ReportDistributionRepository
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.repositories.report_statistics import ReportStatisticsRepository
from app.repositories.report_template import ReportTemplateRepository

_TOP_N = 10
"""How many entries a "popular" ranking keeps.

Unbounded rankings turn the statistics row into an ever-growing blob;
ten is what a dashboard shows.
"""


class ReportStatisticsService:
    """Computes and caches an organization's reporting analytics."""

    def __init__(
        self,
        statistics: ReportStatisticsRepository,
        jobs: ReportJobRepository,
        executions: ReportExecutionRepository,
        exports: ReportExportRepository,
        distributions: ReportDistributionRepository,
        schedules: ReportScheduleRepository,
        templates: ReportTemplateRepository,
    ) -> None:
        self._statistics = statistics
        self._jobs = jobs
        self._executions = executions
        self._exports = exports
        self._distributions = distributions
        self._schedules = schedules
        self._templates = templates

    async def get_for_org(self, organization_id: UUID) -> ReportStatistics:
        """Return the cached rollup, computing it if absent."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> ReportStatistics:
        """Recompute the rollup from live data and store it."""
        jobs = await self._jobs.list_for_org(organization_id)
        executions = await self._executions.list_for_org(organization_id, limit=10_000)
        exports = await self._exports.list_for_org(organization_id, limit=10_000)
        distributions = await self._distributions.list_for_org(organization_id, limit=10_000)
        schedules = await self._schedules.list_for_org(organization_id)
        templates = await self._templates.list_for_org(organization_id)

        job_names = {job.id: job.name for job in jobs}
        template_names = {template.id: template.name for template in templates}

        succeeded = sum(
            1 for execution in executions if execution.status == ReportExecutionStatus.SUCCEEDED
        )
        failed = sum(
            1 for execution in executions if execution.status == ReportExecutionStatus.FAILED
        )
        scheduled = sum(1 for execution in executions if execution.schedule_id is not None)

        durations = [
            execution.duration_ms for execution in executions if execution.duration_ms is not None
        ]
        average_duration = sum(durations) / len(durations) if durations else 0.0

        popular = Counter(
            job_names.get(execution.job_id, str(execution.job_id)) for execution in executions
        )
        formats = Counter(str(export.export_format) for export in exports)
        template_usage = Counter(
            template_names.get(job.template_id, str(job.template_id))
            for job in jobs
            if job.template_id is not None
        )
        schedule_usage = Counter(str(schedule.frequency) for schedule in schedules)
        distribution_usage = Counter(str(record.channel) for record in distributions)
        failed_distributions = sum(
            1 for record in distributions if record.status == DistributionStatus.FAILED
        )

        snapshot = ReportStatistics(
            organization_id=organization_id,
            total_reports=len(jobs),
            total_executions=len(executions),
            successful_executions=succeeded,
            failed_executions=failed,
            scheduled_executions=scheduled,
            total_downloads=sum(export.download_count for export in exports),
            total_distributions=len(distributions),
            failed_distributions=failed_distributions,
            average_duration_ms=average_duration,
            popular_reports=dict(popular.most_common(_TOP_N)),
            export_format_usage=dict(formats),
            template_usage=dict(template_usage.most_common(_TOP_N)),
            schedule_usage=dict(schedule_usage),
            distribution_usage=dict(distribution_usage),
            computed_at=datetime.now(UTC),
        )

        existing = await self._statistics.get_for_org(organization_id)
        if existing is None:
            return await self._statistics.create(snapshot)

        for field in (
            "total_reports",
            "total_executions",
            "successful_executions",
            "failed_executions",
            "scheduled_executions",
            "total_downloads",
            "total_distributions",
            "failed_distributions",
            "average_duration_ms",
            "popular_reports",
            "export_format_usage",
            "template_usage",
            "schedule_usage",
            "distribution_usage",
            "computed_at",
        ):
            setattr(existing, field, getattr(snapshot, field))
        return await self._statistics.update(existing)


__all__ = ["ReportStatisticsService"]
