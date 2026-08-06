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
from app.models.governance import WebhookAudit, WebhookReport, WebhookStatistic
from app.repositories.delivery import WebhookDeliveryAttemptRepository
from app.repositories.event import WebhookEventRepository
from app.repositories.governance import (
    WebhookAuditRepository,
    WebhookReportRepository,
    WebhookStatisticRepository,
)
from app.repositories.retry import WebhookDeadLetterRepository

logger = get_logger("app.services.reporting")

_SUCCESS_STATUS_CEILING = 400
"""Below this HTTP status, a delivery attempt counts as successful."""


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self, statistics: WebhookStatisticRepository, attempts: WebhookDeliveryAttemptRepository
    ) -> None:
        self._statistics = statistics
        self._attempts = attempts

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> WebhookStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate.
        """
        attempts = await self._attempts.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        succeeded = sum(
            1 for a in attempts if a.status_code is not None and a.status_code < _SUCCESS_STATUS_CEILING
        )
        failed = len(attempts) - succeeded
        retries = sum(1 for a in attempts if a.attempt_number > 1)

        latencies = sorted(a.latency_ms for a in attempts if a.latency_ms is not None)
        average_latency = (sum(latencies) / len(latencies)) if latencies else None
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else None

        by_endpoint: dict[str, int] = {}
        for attempt in attempts:
            key = str(attempt.delivery_id)
            by_endpoint[key] = by_endpoint.get(key, 0) + 1

        total = len(attempts)
        success_rate = (succeeded / total * 100) if total else 100.0

        existing = await self._statistics.get_for_window(organization_id, window_start)
        window = existing or WebhookStatistic(organization_id=organization_id, window_start=window_start)
        window.window_end = window_end
        window.deliveries_attempted = total
        window.deliveries_succeeded = succeeded
        window.deliveries_failed = failed
        window.retries = retries
        window.average_latency_ms = average_latency
        window.p95_latency_ms = p95_latency
        window.success_rate = success_rate
        window.by_endpoint = by_endpoint

        return await (self._statistics.update(window) if existing else self._statistics.create(window))

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        latest = await self._statistics.latest(organization_id)
        return {
            "latest_window": {
                "deliveries_attempted": latest.deliveries_attempted if latest else None,
                "success_rate": latest.success_rate if latest else None,
                "average_latency_ms": latest.average_latency_ms if latest else None,
                "p95_latency_ms": latest.p95_latency_ms if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            }
        }

    async def trend(self, organization_id: UUID, *, since_days: int = 30) -> list[WebhookStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/057's REPORTING section asks for.

    Only ``DELIVERY``/``FAILURE``/``RETRY``/``AUDIT`` have real
    builders; ``ENDPOINT``/``REPLAY``/``SECURITY`` return empty rows --
    the same "not every report kind needs a bespoke builder in the
    first cut" scope decision established across every prior AI-IOS
    service's own ``ReportService``.
    """

    def __init__(
        self,
        reports: WebhookReportRepository,
        attempts: WebhookDeliveryAttemptRepository,
        events: WebhookEventRepository,
        dead_letters: WebhookDeadLetterRepository,
        audits: WebhookAuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._attempts = attempts
        self._events = events
        self._dead_letters = dead_letters
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
    ) -> WebhookReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            WebhookReport(
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

    async def _build_delivery(self, organization_id: UUID) -> dict[str, Any]:
        events = await self._events.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {"event_type": one.event_type, "kind": str(one.kind), "created_at": one.created_at.isoformat()}
                for one in events
            ]
        }

    async def _build_failure(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._dead_letters.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "delivery_id": str(one.delivery_id),
                    "endpoint_id": str(one.endpoint_id),
                    "attempt_count": one.attempt_count,
                    "last_error": one.last_error,
                    "dead_lettered_at": one.dead_lettered_at.isoformat(),
                }
                for one in rows
            ]
        }

    async def _build_retry(self, organization_id: UUID) -> dict[str, Any]:
        return await self._build_failure(organization_id)

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
        ReportKind.DELIVERY: _build_delivery,
        ReportKind.FAILURE: _build_failure,
        ReportKind.RETRY: _build_retry,
        ReportKind.AUDIT: _build_audit,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> WebhookReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[WebhookReport]:
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
    """Writes and reads the append-only webhook-service audit trail."""

    def __init__(
        self,
        audits: WebhookAuditRepository,
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
    ) -> WebhookAudit:
        """Append one entry."""
        return await self._audits.create(
            WebhookAudit(
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
            await WebhookAuditRepository(session).create(
                WebhookAudit(
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
        limit: int = 200,
        offset: int = 0,
    ) -> list[WebhookAudit]:
        """Audit entries, newest first."""
        return await self._audits.list_for_org(
            organization_id, action=action, entity_id=entity_id, limit=limit, offset=offset
        )

    async def summary(self, organization_id: UUID, *, days: int = 30) -> dict[str, Any]:
        """How much of each action has happened lately."""
        since = datetime.now(UTC) - timedelta(days=days)
        counts = await self._audits.count_by_action(organization_id, since=since)
        return {"since": since.isoformat(), "total": sum(counts.values()), "by_action": counts}


__all__ = ["AuditService", "ReportService", "StatisticsService"]
