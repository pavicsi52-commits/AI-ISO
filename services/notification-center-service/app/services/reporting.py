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
from app.models.governance import NotificationAudit, NotificationReport, NotificationStatistic
from app.repositories.delivery import NotificationDeliveryRepository
from app.repositories.governance import (
    NotificationAuditRepository,
    NotificationReportRepository,
    NotificationStatisticRepository,
)
from app.repositories.notification import NotificationRepository
from app.repositories.retry import NotificationDeadLetterRepository, NotificationRetryQueueRepository

logger = get_logger("app.services.reporting")

_SUCCESS_STATUSES = frozenset({"sent", "delivered", "read", "acknowledged"})


class StatisticsService:
    """Rolls activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: NotificationStatisticRepository,
        notifications: NotificationRepository,
        deliveries: NotificationDeliveryRepository,
    ) -> None:
        self._statistics = statistics
        self._notifications = notifications
        self._deliveries = deliveries

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> NotificationStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate.
        """
        notifications = await self._notifications.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )
        deliveries = await self._deliveries.list_created_in_window(
            organization_id, start=window_start, end=window_end
        )

        sent_count = sum(1 for row in deliveries if str(row.status) in _SUCCESS_STATUSES)
        delivered_count = sum(1 for row in deliveries if str(row.status) == "delivered")
        failed_count = sum(1 for row in deliveries if str(row.status) == "failed")
        read_count = sum(1 for row in notifications if row.read_at is not None)
        acknowledged_count = sum(1 for row in notifications if row.acknowledged_at is not None)
        retried_count = sum(1 for row in deliveries if row.attempts_used > 1)

        latencies = [row.latency_ms for row in deliveries if row.latency_ms is not None]
        channel_usage: dict[str, int] = {}
        for row in deliveries:
            channel_usage[str(row.channel)] = channel_usage.get(str(row.channel), 0) + 1
        template_usage: dict[str, int] = {}
        for notification in notifications:
            key = str(notification.template_id) if notification.template_id else "none"
            template_usage[key] = template_usage.get(key, 0) + 1

        read_rate = (read_count / len(notifications) * 100) if notifications else 0.0
        acknowledgement_rate = (
            (acknowledged_count / len(notifications) * 100) if notifications else 0.0
        )
        retry_rate = (retried_count / len(deliveries) * 100) if deliveries else 0.0

        existing = await self._statistics.get_for_window(organization_id, window_start)
        window = existing or NotificationStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.sent_count = sent_count
        window.delivered_count = delivered_count
        window.failed_count = failed_count
        window.read_count = read_count
        window.acknowledged_count = acknowledged_count
        window.retried_count = retried_count
        window.average_delivery_ms = (sum(latencies) / len(latencies)) if latencies else None
        window.read_rate = read_rate
        window.acknowledgement_rate = acknowledgement_rate
        window.retry_rate = retry_rate
        window.channel_usage = channel_usage
        window.template_usage = template_usage

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        by_status = await self._deliveries.count_by_status(organization_id)
        latest = await self._statistics.latest(organization_id)
        return {
            "deliveries_by_status": by_status,
            "queue_length": by_status.get("queued", 0),
            "latest_window": {
                "read_rate": latest.read_rate if latest else None,
                "retry_rate": latest.retry_rate if latest else None,
                "average_delivery_ms": latest.average_delivery_ms if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            },
        }

    async def trend(
        self, organization_id: UUID, *, since_days: int = 30
    ) -> list[NotificationStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/055's REPORTING section asks for.

    Only ``DELIVERY``/``FAILURE``/``RETRY``/``AUDIT`` have real builders;
    ``ANNOUNCEMENT``/``TEMPLATE_USAGE``/``CHANNEL``/``ENGAGEMENT`` return
    empty rows -- the same "not every report kind needs a bespoke
    builder in the first cut" scope decision Prompt 054's own
    ``ReportService`` already established.
    """

    def __init__(
        self,
        reports: NotificationReportRepository,
        deliveries: NotificationDeliveryRepository,
        dead_letters: NotificationDeadLetterRepository,
        retry_queue: NotificationRetryQueueRepository,
        audits: NotificationAuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._deliveries = deliveries
        self._dead_letters = dead_letters
        self._retry_queue = retry_queue
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
    ) -> NotificationReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            NotificationReport(
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
        rows = await self._deliveries.list_recent(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "notification_id": str(one.notification_id),
                    "channel": str(one.channel),
                    "status": str(one.status),
                    "queued_at": one.queued_at.isoformat(),
                    "latency_ms": one.latency_ms,
                }
                for one in rows
            ]
        }

    async def _build_failure(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._dead_letters.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "notification_id": str(one.notification_id),
                    "delivery_id": str(one.delivery_id),
                    "channel": str(one.channel),
                    "attempts": one.attempts,
                    "last_error": one.last_error,
                    "dead_lettered_at": one.dead_lettered_at.isoformat(),
                    "resolved": one.resolved,
                }
                for one in rows
            ]
        }

    async def _build_retry(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._retry_queue.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "notification_id": str(one.notification_id),
                    "delivery_id": str(one.delivery_id),
                    "retry_count": one.retry_count,
                    "next_retry_at": one.next_retry_at.isoformat(),
                    "resolved": one.resolved,
                }
                for one in rows
            ]
        }

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

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> NotificationReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[NotificationReport]:
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
    """Writes and reads the append-only notification audit trail."""

    def __init__(
        self,
        audits: NotificationAuditRepository,
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
    ) -> NotificationAudit:
        """Append one entry."""
        return await self._audits.create(
            NotificationAudit(
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
            await NotificationAuditRepository(session).create(
                NotificationAudit(
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
    ) -> list[NotificationAudit]:
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
