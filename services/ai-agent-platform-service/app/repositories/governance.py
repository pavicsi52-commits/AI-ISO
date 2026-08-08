"""Repositories for :class:`app.models.governance.AgentStatistic`,
:class:`~app.models.governance.AgentReport`, and
:class:`~app.models.governance.AgentAudit`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReportKind
from app.models.governance import AgentAudit, AgentReport, AgentStatistic


class AgentStatisticRepository(BaseRepository[AgentStatistic]):
    """CRUD plus lookup for :class:`AgentStatistic`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentStatistic, tenant_scope=tenant_scope)

    async def latest(self, organization_id: UUID) -> AgentStatistic | None:
        """The most recently rolled-up window for *organization_id*."""
        stmt = (
            self._base_select()
            .where(AgentStatistic.organization_id == organization_id)
            .order_by(AgentStatistic.window_start.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(self, organization_id: UUID, *, since: datetime) -> list[AgentStatistic]:
        """Every window for *organization_id* starting at or after *since*."""
        stmt = self._base_select().where(
            AgentStatistic.organization_id == organization_id,
            AgentStatistic.window_start >= since,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AgentReportRepository(BaseRepository[AgentReport]):
    """CRUD plus lookup for :class:`AgentReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> AgentReport:
        """Return *report_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such report exists in that organization.
        """
        stmt = self._base_select().where(
            AgentReport.id == report_id, AgentReport.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        found: AgentReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentReport {report_id!s} was not found in organization {organization_id!s}."
            )
        return found

    async def list_for_org(
        self, organization_id: UUID, *, kind: ReportKind | None = None
    ) -> list[AgentReport]:
        """Every report for *organization_id*, newest first, optionally
        narrowed to one *kind*."""
        stmt = self._base_select().where(AgentReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(AgentReport.kind == kind)
        stmt = stmt.order_by(AgentReport.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AgentAuditRepository(BaseRepository[AgentAudit]):
    """CRUD plus lookup for :class:`AgentAudit`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentAudit, tenant_scope=tenant_scope)

    async def list_for_entity(self, entity_type: str, entity_id: UUID) -> list[AgentAudit]:
        """Every audit row recorded against one specific entity, newest first."""
        stmt = (
            self._base_select()
            .where(AgentAudit.entity_type == entity_type, AgentAudit.entity_id == entity_id)
            .order_by(AgentAudit.occurred_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID, *, limit: int = 100) -> list[AgentAudit]:
        """*organization_id*'s own most recent audit rows, newest first."""
        stmt = (
            self._base_select()
            .where(AgentAudit.organization_id == organization_id)
            .order_by(AgentAudit.occurred_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many audit rows of each :class:`AuditAction` were
        recorded for *organization_id* since *since* -- backs the
        reporting service's own audit-summary view.
        """
        stmt = (
            self._base_select()
            .where(AgentAudit.organization_id == organization_id, AgentAudit.occurred_at >= since)
            .with_only_columns(AgentAudit.action, func.count())
            .group_by(AgentAudit.action)
        )
        result = await self._session.execute(stmt)
        return {str(action): count for action, count in result.all()}


__all__ = [
    "AgentAuditRepository",
    "AgentReportRepository",
    "AgentStatisticRepository",
]
