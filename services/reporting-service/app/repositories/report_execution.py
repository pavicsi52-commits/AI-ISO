"""Repository for :class:`app.models.report_execution.ReportExecution`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReportExecutionStatus
from app.models.report_execution import ReportExecution


class ReportExecutionRepository(BaseRepository[ReportExecution]):
    """CRUD plus lookups for :class:`ReportExecution`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportExecution, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ReportExecutionStatus | None = None,
        limit: int = 200,
    ) -> list[ReportExecution]:
        """Executions for *organization_id*, most recent first."""
        stmt = self._base_select().where(ReportExecution.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ReportExecution.status == status)
        stmt = stmt.order_by(desc(ReportExecution.created_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID, *, limit: int = 100) -> list[ReportExecution]:
        """Executions of one report, most recent first."""
        stmt = (
            self._base_select()
            .where(ReportExecution.job_id == job_id)
            .order_by(desc(ReportExecution.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_job(self, job_id: UUID) -> ReportExecution | None:
        """The most recent execution of one report, if any."""
        executions = await self.list_for_job(job_id, limit=1)
        return executions[0] if executions else None


__all__ = ["ReportExecutionRepository"]
