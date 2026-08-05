"""The API statistic, report, and audit repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction, ReportKind
from app.models.governance import ApiAudit, ApiReport, ApiStatistic


class ApiStatisticRepository(BaseRepository[ApiStatistic]):
    """One rolled-up reporting window."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiStatistic, tenant_scope=tenant_scope)

    async def get_for_window(
        self, organization_id: UUID, window_start: datetime
    ) -> ApiStatistic | None:
        """The rollup row for one exact window, if it already exists."""
        stmt = (
            self._base_select()
            .where(ApiStatistic.organization_id == organization_id)
            .where(ApiStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest(self, organization_id: UUID) -> ApiStatistic | None:
        """The most recently rolled-up window."""
        stmt = (
            self._base_select()
            .where(ApiStatistic.organization_id == organization_id)
            .order_by(ApiStatistic.window_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_since(self, organization_id: UUID, *, since: datetime) -> list[ApiStatistic]:
        """Every window starting on or after *since*, oldest first."""
        stmt = (
            self._base_select()
            .where(ApiStatistic.organization_id == organization_id)
            .where(ApiStatistic.window_start >= since)
            .order_by(ApiStatistic.window_start)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ApiReportRepository(BaseRepository[ApiReport]):
    """One generated document."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> ApiReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ApiReport.organization_id == organization_id)
            .where(ApiReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: ApiReport | None = result.scalars().first()
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
    ) -> list[ApiReport]:
        """Reports generated in this organization, newest first."""
        stmt = self._base_select().where(ApiReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(ApiReport.kind == str(kind))
        stmt = stmt.order_by(ApiReport.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ApiAuditRepository(BaseRepository[ApiAudit]):
    """The append-only audit trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ApiAudit]:
        """Audit entries matching a caller's filters, newest first."""
        stmt = self._base_select().where(ApiAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(ApiAudit.action == str(action))
        if entity_id is not None:
            stmt = stmt.where(ApiAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(ApiAudit.actor_id == actor_id)
        stmt = stmt.order_by(ApiAudit.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How much of each action has happened since *since*."""
        stmt = (
            select(ApiAudit.action, func.count())
            .where(ApiAudit.organization_id == organization_id)
            .where(ApiAudit.occurred_at >= since)
            .group_by(ApiAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = ["ApiAuditRepository", "ApiReportRepository", "ApiStatisticRepository"]
