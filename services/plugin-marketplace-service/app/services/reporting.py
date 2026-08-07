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

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus, ReviewStatus
from app.models.governance import PluginAudit, PluginReport, PluginStatistic
from app.repositories.governance import (
    PluginAuditRepository,
    PluginReportRepository,
    PluginStatisticRepository,
)
from app.repositories.installation import PluginInstallationRepository
from app.repositories.plugin import PluginRepository
from app.repositories.publisher import PluginPublisherRepository
from app.repositories.review import PluginReviewRepository

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls marketplace activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: PluginStatisticRepository,
        plugins: PluginRepository,
        installations: PluginInstallationRepository,
        reviews: PluginReviewRepository,
    ) -> None:
        self._statistics = statistics
        self._plugins = plugins
        self._installations = installations
        self._reviews = reviews

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> PluginStatistic:
        """Compute and store one window's statistics.

        Idempotent by window start: a re-run for a window that already
        has a row updates it rather than creating a duplicate.
        """
        plugins = await self._plugins.list_for_org(organization_id, limit=100_000)
        published_in_window = [p for p in plugins if window_start <= p.created_at < window_end]
        installations = await self._installations.list_for_org(organization_id, limit=100_000)
        in_window = [i for i in installations if window_start <= i.created_at < window_end]
        succeeded = sum(1 for i in in_window if i.status.value != "failed")
        failed = sum(1 for i in in_window if i.status.value == "failed")

        by_category: dict[str, int] = {}
        for plugin in plugins:
            key = str(plugin.category)
            by_category[key] = by_category.get(key, 0) + 1

        reviews_submitted = 0
        rating_total = 0.0
        rating_count = 0
        for plugin in plugins:
            plugin_reviews = await self._reviews.list_all_for_plugin(plugin.id)
            in_window_reviews = [
                r
                for r in plugin_reviews
                if window_start <= r.created_at < window_end and r.status == ReviewStatus.PUBLISHED
            ]
            reviews_submitted += len(in_window_reviews)
            rating_total += sum(r.rating for r in in_window_reviews)
            rating_count += len(in_window_reviews)

        existing = await self._statistics.get_for_window(organization_id, window_start)
        window = existing or PluginStatistic(
            organization_id=organization_id, window_start=window_start
        )
        window.window_end = window_end
        window.plugins_published = len(published_in_window)
        window.installations_attempted = len(in_window)
        window.installations_succeeded = succeeded
        window.installations_failed = failed
        window.upgrades_completed = 0
        window.rollbacks_completed = 0
        window.reviews_submitted = reviews_submitted
        window.average_rating = (rating_total / rating_count) if rating_count else None
        window.by_category = by_category

        return await (
            self._statistics.update(window) if existing else self._statistics.create(window)
        )

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        latest = await self._statistics.latest(organization_id)
        return {
            "latest_window": {
                "plugins_published": latest.plugins_published if latest else None,
                "installations_attempted": latest.installations_attempted if latest else None,
                "average_rating": latest.average_rating if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            }
        }

    async def trend(self, organization_id: UUID, *, since_days: int = 30) -> list[PluginStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/059's own "REPORTING" section asks for.

    Only ``MARKETPLACE``/``PUBLISHER``/``INSTALLATION``/``AUDIT`` have
    real builders; ``PLUGIN_HEALTH``/``COMPATIBILITY``/``SECURITY``
    return empty rows -- the same "not every report kind needs a bespoke
    builder in the first cut" scope decision established across every
    prior AI-IOS service's own ``ReportService``.
    """

    def __init__(
        self,
        reports: PluginReportRepository,
        plugins: PluginRepository,
        installations: PluginInstallationRepository,
        publishers: PluginPublisherRepository,
        audits: PluginAuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._plugins = plugins
        self._installations = installations
        self._publishers = publishers
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
    ) -> PluginReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is recorded
        on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            PluginReport(
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

    async def _build_marketplace(self, organization_id: UUID) -> dict[str, Any]:
        plugins = await self._plugins.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "name": one.name,
                    "category": str(one.category),
                    "status": str(one.status),
                    "current_version_number": one.current_version_number,
                }
                for one in plugins
            ]
        }

    async def _build_publisher(self, organization_id: UUID) -> dict[str, Any]:
        publishers = await self._publishers.list_for_org(organization_id)
        return {
            "rows": [
                {
                    "display_name": one.display_name,
                    "verification_status": str(one.verification_status),
                    "published_plugin_count": one.published_plugin_count,
                }
                for one in publishers
            ]
        }

    async def _build_installation(self, organization_id: UUID) -> dict[str, Any]:
        installations = await self._installations.list_for_org(
            organization_id, limit=self._max_rows
        )
        return {
            "rows": [
                {
                    "plugin_id": str(one.plugin_id),
                    "status": str(one.status),
                    "installed_version_number": one.installed_version_number,
                    "installed_at": one.installed_at.isoformat(),
                }
                for one in installations
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
        ReportKind.MARKETPLACE: _build_marketplace,
        ReportKind.PUBLISHER: _build_publisher,
        ReportKind.INSTALLATION: _build_installation,
        ReportKind.AUDIT: _build_audit,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> PluginReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[PluginReport]:
        """Reports, newest first."""
        return await self._reports.list_for_org(organization_id, limit=limit)

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
    """Writes and reads the append-only plugin-marketplace-service audit trail."""

    def __init__(
        self,
        audits: PluginAuditRepository,
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
    ) -> PluginAudit:
        """Append one entry."""
        return await self._audits.create(
            PluginAudit(
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
            await PluginAuditRepository(session).create(
                PluginAudit(
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
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginAudit]:
        """Audit entries, newest first."""
        return await self._audits.list_for_org(
            organization_id, action=action, limit=limit, offset=offset
        )

    async def summary(self, organization_id: UUID, *, days: int = 30) -> dict[str, Any]:
        """How much of each action has happened lately."""
        since = datetime.now(UTC) - timedelta(days=days)
        counts = await self._audits.count_by_action(organization_id, since=since)
        return {"since": since.isoformat(), "total": sum(counts.values()), "by_action": counts}


__all__ = ["AuditService", "ReportService", "StatisticsService"]
