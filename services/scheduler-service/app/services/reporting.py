"""Statistics rollup, generated reports, and the append-only audit trail."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from shared_core.database.session import session_scope
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import (
    TERMINAL_EXECUTION_STATUSES,
    AuditAction,
    ReportFormat,
    ReportKind,
    ReportStatus,
)
from app.models.governance import SchedulerAudit, SchedulerReport, SchedulerStatistic
from app.repositories.execution import JobExecutionRepository
from app.repositories.governance import (
    SchedulerAuditRepository,
    SchedulerReportRepository,
    SchedulerStatisticRepository,
)
from app.repositories.history import JobFailureRepository
from app.repositories.job import ScheduledJobRepository

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: SchedulerStatisticRepository,
        jobs: ScheduledJobRepository,
        executions: JobExecutionRepository,
    ) -> None:
        self._statistics = statistics
        self._jobs = jobs
        self._executions = executions

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> SchedulerStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate.
        """
        created_jobs = await self._jobs.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        executions = await self._executions.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )

        completed = failed = cancelled = retried = 0
        by_job_type: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        durations: list[float] = []
        for row in executions:
            if row.status == "completed":
                completed += 1
            if row.status == "failed":
                failed += 1
            if row.status == "cancelled":
                cancelled += 1
            if row.attempt_number > 1:
                retried += 1
            by_priority[str(row.priority_snapshot)] = (
                by_priority.get(str(row.priority_snapshot), 0) + 1
            )
            if row.duration_ms is not None:
                durations.append(row.duration_ms / 1_000)

        for job in created_jobs:
            by_job_type[str(job.job_type)] = by_job_type.get(str(job.job_type), 0) + 1

        terminal_total = sum(
            1
            for row in executions
            if row.status in {str(one) for one in TERMINAL_EXECUTION_STATUSES}
        )
        success_rate = (completed / terminal_total * 100) if terminal_total else 100.0
        retry_rate = (retried / len(executions) * 100) if executions else 0.0

        existing = await self._statistics.get_for_window(organization_id, window_start=window_start)
        window = existing or SchedulerStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.jobs_scheduled = len(created_jobs)
        window.jobs_completed = completed
        window.jobs_failed = failed
        window.jobs_cancelled = cancelled
        window.retry_rate = retry_rate
        window.avg_queue_length = float(len(await self._executions.list_open(organization_id)))
        window.avg_execution_time_seconds = (sum(durations) / len(durations)) if durations else None
        window.success_rate = success_rate
        window.by_job_type = by_job_type
        window.by_priority = by_priority

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        by_status = await self._jobs.count_by_status(organization_id)
        open_executions = await self._executions.list_open(organization_id)
        latest = await self._statistics.latest(organization_id)
        return {
            "jobs_by_status": by_status,
            "queue_length": len(open_executions),
            "latest_window": {
                "success_rate": latest.success_rate if latest else None,
                "retry_rate": latest.retry_rate if latest else None,
                "avg_execution_time_seconds": latest.avg_execution_time_seconds if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            },
        }

    async def trend(
        self, organization_id: UUID, *, since_days: int = 30
    ) -> list[SchedulerStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/054's REPORTING section asks for."""

    def __init__(
        self,
        reports: SchedulerReportRepository,
        jobs: ScheduledJobRepository,
        executions: JobExecutionRepository,
        failures: JobFailureRepository,
        statistics: StatisticsService,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._jobs = jobs
        self._executions = executions
        self._failures = failures
        self._statistics = statistics
        self._max_rows = max_rows

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        report_format: ReportFormat = ReportFormat.JSON,
        title: str | None = None,
        generated_by: str | None = None,
    ) -> SchedulerReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            SchedulerReport(
                organization_id=organization_id,
                kind=kind,
                report_format=report_format,
                title=title or f"{kind!s} report",
                status=ReportStatus.RUNNING,
                generated_by=generated_by,
            )
        )
        try:
            content = await self._build(organization_id, kind)
        except Exception as exc:
            record.status = ReportStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "Could not build a report.",
                extra={"extra_fields": {"kind": str(kind), "error": str(exc)}},
            )
            return await self._reports.update(record)

        record.status = ReportStatus.COMPLETED
        record.content = content
        record.row_count = len(content.get("rows", []))
        record.generated_at = datetime.now(UTC)
        record.duration_ms = (record.generated_at - started).total_seconds() * 1_000
        return await self._reports.update(record)

    async def _build(self, organization_id: UUID, kind: ReportKind) -> dict[str, Any]:
        builder = self._BUILDERS.get(kind)
        return await builder(self, organization_id) if builder else {"rows": []}

    async def _build_execution(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._executions.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "job_id": str(one.job_id),
                    "status": str(one.status),
                    "trigger_source": one.trigger_source,
                    "queued_at": one.queued_at.isoformat(),
                    "duration_ms": one.duration_ms,
                }
                for one in rows
            ]
        }

    async def _build_failure(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._failures.list_unrecovered_terminal(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "job_id": str(one.job_id),
                    "execution_id": str(one.execution_id),
                    "failure_reason": one.failure_reason,
                    "occurred_at": one.occurred_at.isoformat(),
                }
                for one in rows
            ]
        }

    async def _build_performance(self, organization_id: UUID) -> dict[str, Any]:
        dashboard = await self._statistics.dashboard(organization_id)
        return {"rows": [dashboard]}

    _BUILDERS: ClassVar[dict[ReportKind, Any]] = {
        ReportKind.EXECUTION: _build_execution,
        ReportKind.FAILURE: _build_failure,
        ReportKind.PERFORMANCE: _build_performance,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> SchedulerReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[SchedulerReport]:
        """Reports, newest first."""
        return await self._reports.list_for_org(organization_id, limit=limit, offset=offset)

    @staticmethod
    def to_csv(content: dict[str, Any]) -> str:
        """Render a report's rows as CSV."""
        rows = content.get("rows", [])
        if not rows:
            return ""
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()

    @staticmethod
    def to_markdown(content: dict[str, Any], *, title: str = "Report") -> str:
        """Render a report's rows as a Markdown table."""
        rows = content.get("rows", [])
        lines = [f"# {title}", ""]
        if not rows:
            lines.append("No rows.")
            return "\n".join(lines)
        headers = list(rows[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        return "\n".join(lines)


class AuditService:
    """Writes and reads the append-only scheduler audit trail."""

    def __init__(
        self,
        audits: SchedulerAuditRepository,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._audits = audits
        self._session_factory = session_factory

    async def record(
        self,
        organization_id: UUID,
        *,
        action: AuditAction,
        entity_type: str,
        summary: str,
        entity_id: UUID | None = None,
        entity_reference: str | None = None,
        actor_id: str | None = None,
        actor_type: str = "user",
        succeeded: bool = True,
        changes: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> SchedulerAudit:
        """Append one entry."""
        return await self._audits.create(
            SchedulerAudit(
                organization_id=organization_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_reference=entity_reference,
                actor_id=actor_id,
                actor_type=actor_type,
                occurred_at=datetime.now(UTC),
                summary=summary,
                succeeded=succeeded,
                changes=dict(changes or {}),
                context=dict(context or {}),
                request_id=request_id,
                ip_address=ip_address,
            )
        )

    async def record_failure(
        self,
        organization_id: UUID,
        *,
        action: AuditAction,
        entity_type: str,
        summary: str,
        entity_reference: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Append an entry for an operation that was refused.

        Committed in its **own transaction** -- a refused request's
        transaction rolls back, and an audit row written inside it
        would roll back too, losing the record of the attempt at
        exactly the moment an investigation would ask for it.
        """
        if self._session_factory is None:
            await self.record(
                organization_id,
                action=action,
                entity_type=entity_type,
                summary=summary,
                entity_reference=entity_reference,
                actor_id=actor_id,
                succeeded=False,
                request_id=request_id,
                context=context,
            )
            return

        async with session_scope(self._session_factory) as session:
            await SchedulerAuditRepository(session).create(
                SchedulerAudit(
                    organization_id=organization_id,
                    action=action,
                    entity_type=entity_type,
                    entity_reference=entity_reference,
                    actor_id=actor_id,
                    actor_type="user",
                    occurred_at=datetime.now(UTC),
                    summary=summary,
                    succeeded=False,
                    request_id=request_id,
                    context=dict(context or {}),
                )
            )

    async def list_entries(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SchedulerAudit]:
        """Audit entries, newest first."""
        return await self._audits.list_for_org(
            organization_id,
            action=action,
            entity_id=entity_id,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        )

    async def summary(self, organization_id: UUID, *, days: int = 30) -> dict[str, Any]:
        """How much of each action has happened lately."""
        since = datetime.now(UTC) - timedelta(days=days)
        counts = await self._audits.count_by_action(organization_id, since=since)
        return {"since": since.isoformat(), "total": sum(counts.values()), "by_action": counts}


__all__ = ["AuditService", "ReportService", "StatisticsService"]
