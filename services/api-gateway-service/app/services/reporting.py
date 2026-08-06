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

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus
from app.models.governance import ApiAudit, ApiReport, ApiStatistic
from app.repositories.governance import (
    ApiAuditRepository,
    ApiReportRepository,
    ApiStatisticRepository,
)
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository

logger = get_logger("app.services.reporting")

_SUCCESS_STATUS_CEILING = 400
"""Below this HTTP status, a response counts as successful."""


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: ApiStatisticRepository,
        requests: ApiRequestLogRepository,
        responses: ApiResponseLogRepository,
    ) -> None:
        self._statistics = statistics
        self._requests = requests
        self._responses = responses

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> ApiStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate.
        """
        requests = await self._requests.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        responses = await self._responses.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )

        successful = sum(1 for r in responses if r.status_code < _SUCCESS_STATUS_CEILING)
        failed = len(responses) - successful
        rate_limited = sum(1 for r in responses if r.rate_limited)
        quota_exceeded = sum(1 for r in responses if r.quota_exceeded)

        latencies = sorted(r.latency_ms for r in responses)
        average_latency = (sum(latencies) / len(latencies)) if latencies else None
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else None

        by_service: dict[str, int] = {}
        for request in requests:
            if request.service_id is not None:
                key = str(request.service_id)
                by_service[key] = by_service.get(key, 0) + 1

        by_status_code: dict[str, int] = {}
        for response in responses:
            key = str(response.status_code)
            by_status_code[key] = by_status_code.get(key, 0) + 1

        by_client: dict[str, int] = {}
        for request in requests:
            if request.client_id is not None:
                key = str(request.client_id)
                by_client[key] = by_client.get(key, 0) + 1

        total = len(responses)
        error_rate = (failed / total * 100) if total else 0.0
        success_rate = (successful / total * 100) if total else 100.0

        existing = await self._statistics.get_for_window(organization_id, window_start)
        window = existing or ApiStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.total_requests = len(requests)
        window.successful_requests = successful
        window.failed_requests = failed
        window.rate_limited_requests = rate_limited
        window.quota_exceeded_requests = quota_exceeded
        window.average_latency_ms = average_latency
        window.p95_latency_ms = p95_latency
        window.error_rate = error_rate
        window.success_rate = success_rate
        window.by_service = by_service
        window.by_status_code = by_status_code
        window.by_client = by_client

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        by_status_code = await self._responses.count_by_status_code(organization_id)
        latest = await self._statistics.latest(organization_id)
        return {
            "responses_by_status_code": by_status_code,
            "latest_window": {
                "error_rate": latest.error_rate if latest else None,
                "success_rate": latest.success_rate if latest else None,
                "average_latency_ms": latest.average_latency_ms if latest else None,
                "p95_latency_ms": latest.p95_latency_ms if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            },
        }

    async def trend(self, organization_id: UUID, *, since_days: int = 30) -> list[ApiStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/056's REPORTING section asks for.

    Only ``API_USAGE``/``LATENCY``/``TRAFFIC``/``AUDIT`` have real
    builders; ``QUOTA``/``SECURITY``/``GATEWAY_HEALTH`` return empty
    rows -- the same "not every report kind needs a bespoke builder in
    the first cut" scope decision established across every prior
    AI-IOS service's own ``ReportService``.
    """

    def __init__(
        self,
        reports: ApiReportRepository,
        requests: ApiRequestLogRepository,
        responses: ApiResponseLogRepository,
        audits: ApiAuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._requests = requests
        self._responses = responses
        self._audits = audits
        self._max_rows = max_rows

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        report_format: ReportFormat = ReportFormat.JSON,
        title: str | None = None,
        generated_by: str | None = None,
    ) -> ApiReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            ApiReport(
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

    async def _build_api_usage(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._requests.list_recent(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "method": one.method,
                    "path": one.path,
                    "client_id": str(one.client_id) if one.client_id else None,
                    "started_at": one.started_at.isoformat(),
                }
                for one in rows
            ]
        }

    async def _build_latency(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._responses.list_created_in_window(
            organization_id,
            start=datetime.min.replace(tzinfo=UTC),
            end=datetime.now(UTC),
            limit=self._max_rows,
        )
        return {
            "rows": [
                {
                    "request_id": str(one.request_id),
                    "status_code": one.status_code,
                    "latency_ms": one.latency_ms,
                    "completed_at": one.completed_at.isoformat(),
                }
                for one in rows
            ]
        }

    async def _build_traffic(self, organization_id: UUID) -> dict[str, Any]:
        return await self._build_api_usage(organization_id)

    async def _build_audit(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._audits.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "action": str(one.action),
                    "entity_type": one.entity_type,
                    "actor_id": one.actor_id,
                    "occurred_at": one.occurred_at.isoformat(),
                    "succeeded": one.succeeded,
                }
                for one in rows
            ]
        }

    _BUILDERS: ClassVar[dict[ReportKind, Any]] = {
        ReportKind.API_USAGE: _build_api_usage,
        ReportKind.LATENCY: _build_latency,
        ReportKind.TRAFFIC: _build_traffic,
        ReportKind.AUDIT: _build_audit,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> ApiReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[ApiReport]:
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
    """Writes and reads the append-only gateway audit trail."""

    def __init__(
        self,
        audits: ApiAuditRepository,
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
    ) -> ApiAudit:
        """Append one entry."""
        return await self._audits.create(
            ApiAudit(
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
            await ApiAuditRepository(session).create(
                ApiAudit(
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
    ) -> list[ApiAudit]:
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
