"""Repositories for statistics, generated reports, and the audit trail."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.models.governance import SchedulerAudit, SchedulerReport, SchedulerStatistic


class SchedulerStatisticRepository(BaseRepository[SchedulerStatistic]):
    """Rolled-up statistics windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SchedulerStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, *, window_start: datetime
    ) -> SchedulerStatistic | None:
        """The window starting at exactly *window_start*, if it has been rolled up."""
        stmt = (
            self._base_select()
            .where(SchedulerStatistic.organization_id == organization_id)
            .where(SchedulerStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> SchedulerStatistic | None:
        """The most recently rolled-up window."""
        stmt = (
            self._base_select()
            .where(SchedulerStatistic.organization_id == organization_id)
            .order_by(SchedulerStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(
        self, organization_id: UUID, *, since: datetime
    ) -> list[SchedulerStatistic]:
        """Every window starting on or after *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(SchedulerStatistic.organization_id == organization_id)
            .where(SchedulerStatistic.window_start >= since)
            .order_by(SchedulerStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SchedulerReportRepository(BaseRepository[SchedulerReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SchedulerReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> SchedulerReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(SchedulerReport.organization_id == organization_id)
            .where(SchedulerReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: SchedulerReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[SchedulerReport]:
        """Reports, newest first."""
        stmt = (
            self._base_select()
            .where(SchedulerReport.organization_id == organization_id)
            .order_by(SchedulerReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SchedulerAuditRepository(BaseRepository[SchedulerAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SchedulerAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SchedulerAudit]:
        """Audit entries matching a caller's filters, newest first."""
        stmt = self._base_select().where(SchedulerAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(SchedulerAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(SchedulerAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(SchedulerAudit.actor_id == actor_id)
        stmt = stmt.order_by(SchedulerAudit.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How much of each action has happened since *since*."""
        stmt = (
            select(SchedulerAudit.action, func.count())
            .where(SchedulerAudit.organization_id == organization_id)
            .where(SchedulerAudit.occurred_at >= since)
            .group_by(SchedulerAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = ["SchedulerAuditRepository", "SchedulerReportRepository", "SchedulerStatisticRepository"]
