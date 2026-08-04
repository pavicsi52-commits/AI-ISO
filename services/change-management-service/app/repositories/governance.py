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
from app.models.governance import ChangeAudit, ChangeReport, ChangeStatistic


class ChangeStatisticRepository(BaseRepository[ChangeStatistic]):
    """Rolled-up statistics windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, *, window_start: datetime
    ) -> ChangeStatistic | None:
        """The window starting at exactly *window_start*, if it has been rolled up."""
        stmt = (
            self._base_select()
            .where(ChangeStatistic.organization_id == organization_id)
            .where(ChangeStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> ChangeStatistic | None:
        """The most recently rolled-up window."""
        stmt = (
            self._base_select()
            .where(ChangeStatistic.organization_id == organization_id)
            .order_by(ChangeStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(self, organization_id: UUID, *, since: datetime) -> list[ChangeStatistic]:
        """Every window starting on or after *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(ChangeStatistic.organization_id == organization_id)
            .where(ChangeStatistic.window_start >= since)
            .order_by(ChangeStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeReportRepository(BaseRepository[ChangeReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> ChangeReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeReport.organization_id == organization_id)
            .where(ChangeReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[ChangeReport]:
        """Reports, newest first."""
        stmt = (
            self._base_select()
            .where(ChangeReport.organization_id == organization_id)
            .order_by(ChangeReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeAuditRepository(BaseRepository[ChangeAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ChangeAudit]:
        """Audit entries matching a caller's filters, newest first."""
        stmt = self._base_select().where(ChangeAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(ChangeAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(ChangeAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(ChangeAudit.actor_id == actor_id)
        stmt = stmt.order_by(ChangeAudit.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How much of each action has happened since *since*."""
        stmt = (
            select(ChangeAudit.action, func.count())
            .where(ChangeAudit.organization_id == organization_id)
            .where(ChangeAudit.occurred_at >= since)
            .group_by(ChangeAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = ["ChangeAuditRepository", "ChangeReportRepository", "ChangeStatisticRepository"]
