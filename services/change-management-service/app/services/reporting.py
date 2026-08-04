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

from app.models.enums import AuditAction, JobStatus, ReportFormat, ReportKind
from app.models.governance import ChangeAudit, ChangeReport, ChangeStatistic
from app.repositories.change import ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository
from app.repositories.governance import (
    ChangeAuditRepository,
    ChangeReportRepository,
    ChangeStatisticRepository,
)

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: ChangeStatisticRepository,
        changes: ChangeRequestRepository,
        conflicts: ChangeConflictRepository,
    ) -> None:
        self._statistics = statistics
        self._changes = changes
        self._conflicts = conflicts

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> ChangeStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate, so a
        retried or leader-re-elected sweep cannot double-count a window
        in the trend it feeds.
        """
        created = await self._changes.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        by_status = await self._changes.count_by_status(organization_id)
        open_total = sum(
            count for status, count in by_status.items() if status not in ("closed", "cancelled")
        )

        by_category: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        completed = rolled_back = rejected = cancelled = emergency = 0
        approval_durations: list[float] = []
        implementation_durations: list[float] = []
        for row in created:
            by_category[str(row.category)] = by_category.get(str(row.category), 0) + 1
            if row.risk_level:
                by_risk[str(row.risk_level)] = by_risk.get(str(row.risk_level), 0) + 1
            if row.status == "completed":
                completed += 1
            if row.status == "rolled_back":
                rolled_back += 1
            if row.status == "rejected":
                rejected += 1
            if row.status == "cancelled":
                cancelled += 1
            if row.change_type == "emergency":
                emergency += 1
            if row.approval_duration_seconds is not None:
                approval_durations.append(row.approval_duration_seconds)
            if row.implementation_duration_seconds is not None:
                implementation_durations.append(row.implementation_duration_seconds)

        conflicts_detected = len(
            [
                one
                for one in await self._conflicts.list_active(organization_id)
                if window_start <= one.detected_at < window_end
            ]
        )

        terminal_total = completed + rolled_back + rejected + cancelled
        success_rate = (completed / terminal_total * 100) if terminal_total else 100.0

        existing = await self._statistics.get_for_window(organization_id, window_start=window_start)
        window = existing or ChangeStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.changes_created = len(created)
        window.changes_completed = completed
        window.changes_rolled_back = rolled_back
        window.changes_rejected = rejected
        window.changes_cancelled = cancelled
        window.emergency_changes = emergency
        window.open_total = open_total
        window.success_rate = success_rate
        window.avg_approval_duration_seconds = (
            (sum(approval_durations) / len(approval_durations)) if approval_durations else None
        )
        window.avg_implementation_duration_seconds = (
            (sum(implementation_durations) / len(implementation_durations))
            if implementation_durations
            else None
        )
        window.conflicts_detected = conflicts_detected
        window.by_risk_level = by_risk
        window.by_category = by_category

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        by_status = await self._changes.count_by_status(organization_id)
        latest = await self._statistics.latest(organization_id)
        active_conflicts = await self._conflicts.list_active(organization_id)
        return {
            "by_status": by_status,
            "active_conflicts": len(active_conflicts),
            "latest_window": {
                "success_rate": latest.success_rate if latest else None,
                "avg_approval_duration_seconds": (
                    latest.avg_approval_duration_seconds if latest else None
                ),
                "avg_implementation_duration_seconds": (
                    latest.avg_implementation_duration_seconds if latest else None
                ),
                "computed_through": latest.window_end.isoformat() if latest else None,
            },
        }

    async def trend(self, organization_id: UUID, *, since_days: int = 30) -> list[ChangeStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/053's REPORTING section asks for."""

    def __init__(
        self,
        reports: ChangeReportRepository,
        changes: ChangeRequestRepository,
        statistics: StatisticsService,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._changes = changes
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
    ) -> ChangeReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            ChangeReport(
                organization_id=organization_id,
                kind=kind,
                report_format=report_format,
                title=title or f"{kind!s} report",
                status=JobStatus.RUNNING,
                generated_by=generated_by,
            )
        )
        try:
            content = await self._build(organization_id, kind)
        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "Could not build a report.",
                extra={"extra_fields": {"kind": str(kind), "error": str(exc)}},
            )
            return await self._reports.update(record)

        record.status = JobStatus.COMPLETED
        record.content = content
        record.row_count = len(content.get("rows", []))
        record.generated_at = datetime.now(UTC)
        record.duration_ms = (record.generated_at - started).total_seconds() * 1_000
        return await self._reports.update(record)

    async def _build(self, organization_id: UUID, kind: ReportKind) -> dict[str, Any]:
        # CAB, CALENDAR, IMPLEMENTATION, PIR, and COMPLIANCE reports are
        # each scoped to one change (or one CAB review, one calendar
        # entry) at a time via their own endpoints, not an
        # organization-wide sweep -- the same reasoning Prompt 052
        # applies to ROOT_CAUSE and POSTMORTEM. A bare "generate" for any
        # of them has nothing organization-wide to list.
        builder = self._BUILDERS.get(kind)
        return await builder(self, organization_id) if builder else {"rows": []}

    async def _build_change(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._changes.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "reference": one.reference,
                    "title": one.title,
                    "status": str(one.status),
                    "priority": str(one.priority),
                    "risk_level": one.risk_level,
                }
                for one in rows
            ]
        }

    async def _build_executive(self, organization_id: UUID) -> dict[str, Any]:
        dashboard = await self._statistics.dashboard(organization_id)
        computed_through = dashboard["latest_window"]["computed_through"]
        narrative = (
            "No statistics have been computed yet."
            if computed_through is None
            else (
                f"Change success rate is {dashboard['latest_window']['success_rate']:.1f}% "
                f"as of {computed_through}."
            )
        )
        return {"rows": [dashboard], "narrative": narrative}

    async def _build_risk(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._changes.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {"reference": one.reference, "title": one.title, "risk_level": one.risk_level}
                for one in rows
                if one.risk_level is not None
            ]
        }

    async def _build_trend(self, organization_id: UUID) -> dict[str, Any]:
        windows = await self._statistics.trend(organization_id, since_days=90)
        return {
            "rows": [
                {
                    "window_start": one.window_start.isoformat(),
                    "changes_created": one.changes_created,
                    "success_rate": one.success_rate,
                }
                for one in windows
            ]
        }

    _BUILDERS: ClassVar[dict[ReportKind, Any]] = {
        ReportKind.CHANGE: _build_change,
        ReportKind.EXECUTIVE: _build_executive,
        ReportKind.RISK: _build_risk,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> ChangeReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[ChangeReport]:
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
    """Writes and reads the append-only change audit trail."""

    def __init__(
        self,
        audits: ChangeAuditRepository,
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
    ) -> ChangeAudit:
        """Append one entry."""
        return await self._audits.create(
            ChangeAudit(
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

        Committed in its **own transaction**, the same reasoning
        Prompt 052's ``AuditService.record_failure`` established: a
        refused request's transaction rolls back, and an audit row
        written inside it would roll back too -- losing the record of
        the attempt at exactly the moment an investigation would ask
        for it.
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
            await ChangeAuditRepository(session).create(
                ChangeAudit(
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
    ) -> list[ChangeAudit]:
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
