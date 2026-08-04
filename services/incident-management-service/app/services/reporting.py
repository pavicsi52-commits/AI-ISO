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

from app.incidents.engine import percentile
from app.models.enums import AuditAction, JobStatus, ReportFormat, ReportKind, SlaStatus
from app.models.governance import IncidentAudit, IncidentReport, IncidentStatistic
from app.repositories.governance import AuditRepository, ReportRepository, StatisticRepository
from app.repositories.incident import IncidentRepository
from app.repositories.major import MajorIncidentRepository
from app.repositories.postmortem import PostmortemRepository
from app.repositories.rca import ProblemRepository
from app.repositories.sla import EscalationRepository, SlaRepository
from app.sla.engine import compliance_rate

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: StatisticRepository,
        incidents: IncidentRepository,
        slas: SlaRepository,
        escalations: EscalationRepository,
        major_incidents: MajorIncidentRepository,
        problems: ProblemRepository,
    ) -> None:
        self._statistics = statistics
        self._incidents = incidents
        self._slas = slas
        self._escalations = escalations
        self._major_incidents = major_incidents
        self._problems = problems

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> IncidentStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate, so a
        retried or leader-re-elected sweep cannot double-count a window
        in the trend it feeds.
        """
        created = await self._incidents.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        by_status = await self._incidents.count_by_status(organization_id)
        open_total = sum(
            count
            for status, count in by_status.items()
            if status not in ("closed", "cancelled", "merged")
        )

        by_category: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        mttas: list[float] = []
        mttrs: list[float] = []
        reopened = 0
        for row in created:
            by_category[str(row.category)] = by_category.get(str(row.category), 0) + 1
            by_priority[str(row.priority)] = by_priority.get(str(row.priority), 0) + 1
            if row.mtta_seconds is not None:
                mttas.append(row.mtta_seconds)
            if row.mttr_seconds is not None:
                mttrs.append(row.mttr_seconds)
            if row.reopen_count > 0:
                reopened += 1

        resolved = sum(1 for one in created if one.resolved_at is not None)
        closed = sum(1 for one in created if one.closed_at is not None)
        major = sum(1 for one in created if one.is_major)

        met = await self._slas.count_in_window(
            organization_id, status=SlaStatus.MET, start=window_start, end=window_end
        )
        breached = await self._slas.count_in_window(
            organization_id, status=SlaStatus.BREACHED, start=window_start, end=window_end
        )
        escalations_triggered = await self._escalations.count_in_window(
            organization_id, start=window_start, end=window_end
        )

        existing = await self._statistics.get_for_window(organization_id, window_start=window_start)
        window = existing or IncidentStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.incidents_created = len(created)
        window.incidents_resolved = resolved
        window.incidents_closed = closed
        window.incidents_reopened = reopened
        window.major_incidents = major
        window.open_total = open_total
        window.avg_mtta_seconds = (sum(mttas) / len(mttas)) if mttas else None
        window.avg_mttr_seconds = (sum(mttrs) / len(mttrs)) if mttrs else None
        window.p90_mttr_seconds = percentile(mttrs, pct=90)
        window.sla_met_count = met
        window.sla_breached_count = breached
        window.sla_compliance_rate = compliance_rate(met=met, breached=breached)
        window.escalations_triggered = escalations_triggered
        window.by_category = by_category
        window.by_priority = by_priority

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        by_status = await self._incidents.count_by_status(organization_id)
        latest = await self._statistics.latest(organization_id)
        active_major = await self._major_incidents.list_active(organization_id)
        return {
            "by_status": by_status,
            "active_major_incidents": len(active_major),
            "latest_window": {
                "avg_mtta_seconds": latest.avg_mtta_seconds if latest else None,
                "avg_mttr_seconds": latest.avg_mttr_seconds if latest else None,
                "sla_compliance_rate": latest.sla_compliance_rate if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            },
        }

    async def trend(
        self, organization_id: UUID, *, since_days: int = 30
    ) -> list[IncidentStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/052's REPORTING section asks for."""

    def __init__(
        self,
        reports: ReportRepository,
        incidents: IncidentRepository,
        statistics: StatisticsService,
        major_incidents: MajorIncidentRepository,
        problems: ProblemRepository,
        postmortems: PostmortemRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._incidents = incidents
        self._statistics = statistics
        self._major_incidents = major_incidents
        self._problems = problems
        self._postmortems = postmortems
        self._max_rows = max_rows

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        report_format: ReportFormat = ReportFormat.JSON,
        title: str | None = None,
        generated_by: str | None = None,
    ) -> IncidentReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``. Somebody who
        asked for a report needs to be told what went wrong with it, not
        handed a stack trace.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            IncidentReport(
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
        builder = self._BUILDERS.get(kind)
        # ROOT_CAUSE and POSTMORTEM reports are scoped to one incident at a
        # time via their own endpoints rather than an organization-wide
        # sweep, so a bare "generate" for either has nothing to list.
        return await builder(self, organization_id) if builder else {"rows": []}

    async def _build_incident(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._incidents.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "reference": one.reference,
                    "title": one.title,
                    "status": str(one.status),
                    "priority": str(one.priority),
                    "mttr_seconds": one.mttr_seconds,
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
                f"SLA compliance is "
                f"{dashboard['latest_window']['sla_compliance_rate']:.1f}% as of "
                f"{computed_through}."
            )
        )
        return {"rows": [dashboard], "narrative": narrative}

    async def _build_major_incident(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._major_incidents.list_active(organization_id)
        return {
            "rows": [
                {
                    "incident_id": str(one.incident_id),
                    "declared_at": one.declared_at.isoformat(),
                    "incident_commander_id": one.incident_commander_id,
                    "stood_down_at": (one.stood_down_at.isoformat() if one.stood_down_at else None),
                }
                for one in rows
            ]
        }

    async def _build_sla(self, organization_id: UUID) -> dict[str, Any]:
        latest = await self._statistics.trend(organization_id, since_days=1)
        return {
            "rows": [
                {
                    "window_start": one.window_start.isoformat(),
                    "sla_met_count": one.sla_met_count,
                    "sla_breached_count": one.sla_breached_count,
                    "sla_compliance_rate": one.sla_compliance_rate,
                }
                for one in latest
            ]
        }

    async def _build_problem(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._problems.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "reference": one.reference,
                    "title": one.title,
                    "status": str(one.status),
                    "incident_count": one.incident_count,
                }
                for one in rows
            ]
        }

    async def _build_trend(self, organization_id: UUID) -> dict[str, Any]:
        windows = await self._statistics.trend(organization_id, since_days=90)
        return {
            "rows": [
                {
                    "window_start": one.window_start.isoformat(),
                    "incidents_created": one.incidents_created,
                    "avg_mttr_seconds": one.avg_mttr_seconds,
                }
                for one in windows
            ]
        }

    _BUILDERS: ClassVar[dict[ReportKind, Any]] = {
        ReportKind.INCIDENT: _build_incident,
        ReportKind.EXECUTIVE: _build_executive,
        ReportKind.MAJOR_INCIDENT: _build_major_incident,
        ReportKind.SLA: _build_sla,
        ReportKind.PROBLEM: _build_problem,
        ReportKind.TREND: _build_trend,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> IncidentReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[IncidentReport]:
        """Reports, newest first."""
        return await self._reports.list_for_org(organization_id, limit=limit, offset=offset)

    @staticmethod
    def to_csv(content: dict[str, Any]) -> str:
        """Render a report's rows as CSV.

        Empty rows render as an empty string, not a bare header line --
        a header with nothing under it reads as "something broke," and
        an empty report is a real, if unhelpful, answer.
        """
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
    """Writes and reads the append-only incident audit trail."""

    def __init__(
        self,
        audits: AuditRepository,
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
    ) -> IncidentAudit:
        """Append one entry."""
        return await self._audits.create(
            IncidentAudit(
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
        Prompt 051's ``AuditService.record_failure`` established: a
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
            await AuditRepository(session).create(
                IncidentAudit(
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
    ) -> list[IncidentAudit]:
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
