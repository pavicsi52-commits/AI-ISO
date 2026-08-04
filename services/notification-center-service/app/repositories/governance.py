"""The notification statistic, report, and audit repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction, ReportKind
from app.models.governance import NotificationAudit, NotificationReport, NotificationStatistic


class NotificationStatisticRepository(BaseRepository[NotificationStatistic]):
    """One rolled-up reporting window."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, window_start: datetime
    ) -> NotificationStatistic | None:
        """The rollup row for one exact window, if it already exists."""
        stmt = (
            self._base_select()
            .where(NotificationStatistic.organization_id == organization_id)
            .where(NotificationStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> NotificationStatistic | None:
        """The most recently rolled-up window."""
        stmt = (
            self._base_select()
            .where(NotificationStatistic.organization_id == organization_id)
            .order_by(NotificationStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(
        self, organization_id: UUID, *, since: datetime
    ) -> list[NotificationStatistic]:
        """Every window starting on or after *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(NotificationStatistic.organization_id == organization_id)
            .where(NotificationStatistic.window_start >= since)
            .order_by(NotificationStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_range(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 1_000
    ) -> list[NotificationStatistic]:
        """Every rollup window overlapping ``[start, end)``, oldest first."""
        stmt = (
            self._base_select()
            .where(NotificationStatistic.organization_id == organization_id)
            .where(NotificationStatistic.window_start >= start)
            .where(NotificationStatistic.window_start < end)
            .order_by(NotificationStatistic.window_start)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationReportRepository(BaseRepository[NotificationReport]):
    """One generated document."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> NotificationReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationReport.organization_id == organization_id)
            .where(NotificationReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationReport]:
        """Reports generated in this organization, newest first."""
        stmt = self._base_select().where(NotificationReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(NotificationReport.kind == str(kind))
        stmt = stmt.order_by(NotificationReport.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationAuditRepository(BaseRepository[NotificationAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationAudit]:
        """Audit entries matching a caller's filters, newest first."""
        stmt = self._base_select().where(NotificationAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(NotificationAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(NotificationAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(NotificationAudit.actor_id == actor_id)
        stmt = stmt.order_by(NotificationAudit.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How much of each action has happened since *since*."""
        stmt = (
            select(NotificationAudit.action, func.count())
            .where(NotificationAudit.organization_id == organization_id)
            .where(NotificationAudit.occurred_at >= since)
            .group_by(NotificationAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = [
    "NotificationAuditRepository",
    "NotificationReportRepository",
    "NotificationStatisticRepository",
]
