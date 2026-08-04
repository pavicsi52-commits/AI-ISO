"""Repositories for reports, statistics, and the append-only audit trail."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.models.governance import IncidentAudit, IncidentReport, IncidentStatistic


class ReportRepository(BaseRepository[IncidentReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> IncidentReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(IncidentReport.organization_id == organization_id)
            .where(IncidentReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: IncidentReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[IncidentReport]:
        """Reports, newest first."""
        stmt = (
            self._base_select()
            .where(IncidentReport.organization_id == organization_id)
            .order_by(IncidentReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class StatisticRepository(BaseRepository[IncidentStatistic]):
    """Rolled-up statistics windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, *, window_start: datetime
    ) -> IncidentStatistic | None:
        """The rollup for one window's start, if it has already been computed.

        What the rollup worker checks before writing, so a re-run for a
        window that already exists updates that row rather than creating
        a duplicate.
        """
        stmt = (
            self._base_select()
            .where(IncidentStatistic.organization_id == organization_id)
            .where(IncidentStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(
        self, organization_id: UUID, *, since: datetime, limit: int = 365
    ) -> list[IncidentStatistic]:
        """Windows since a given moment, oldest first -- for trend charts."""
        stmt = (
            self._base_select()
            .where(IncidentStatistic.organization_id == organization_id)
            .where(IncidentStatistic.window_start >= since)
            .order_by(IncidentStatistic.window_start)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest(self, organization_id: UUID) -> IncidentStatistic | None:
        """The most recently computed window."""
        stmt = (
            self._base_select()
            .where(IncidentStatistic.organization_id == organization_id)
            .order_by(IncidentStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class AuditRepository(BaseRepository[IncidentAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[IncidentAudit]:
        """Audit entries matching a caller's filters, newest first."""
        stmt = self._base_select().where(IncidentAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(IncidentAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(IncidentAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(IncidentAudit.actor_id == actor_id)
        stmt = stmt.order_by(IncidentAudit.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many entries of each action landed since a given moment."""
        stmt = (
            select(IncidentAudit.action, func.count())
            .where(IncidentAudit.organization_id == organization_id)
            .where(IncidentAudit.occurred_at >= since)
            .group_by(IncidentAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = ["AuditRepository", "ReportRepository", "StatisticRepository"]
