"""Repositories for job executions and their log lines."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OPEN_EXECUTION_STATUSES, ExecutionStatus
from app.models.execution import JobExecution, JobExecutionLog


class JobExecutionRepository(BaseRepository[JobExecution]):
    """One row per dispatch of one job."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobExecution, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, execution_id: UUID) -> JobExecution:
        """One execution by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.id == execution_id)
        )
        result = await self._session.execute(stmt)
        found: JobExecution | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No execution with id {execution_id} in this organization.")
        return found

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[JobExecution]:
        """Every execution of one job, newest first."""
        stmt = (
            self._base_select()
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.job_id == job_id)
            .order_by(JobExecution.queued_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_job(self, organization_id: UUID, job_id: UUID) -> JobExecution | None:
        """The most recent execution of one job, if any has ever run."""
        stmt = (
            self._base_select()
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.job_id == job_id)
            .order_by(JobExecution.queued_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        job_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[JobExecution]:
        """Executions matching a caller's filters, newest first."""
        stmt = self._base_select().where(JobExecution.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(JobExecution.status == str(status))
        if job_id is not None:
            stmt = stmt.where(JobExecution.job_id == job_id)
        stmt = stmt.order_by(JobExecution.queued_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open(self, organization_id: UUID, *, limit: int = 1_000) -> list[JobExecution]:
        """Every execution still in flight -- queued, running, paused, waiting, or blocked."""
        stmt = (
            self._base_select()
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.status.in_([str(one) for one in OPEN_EXECUTION_STATUSES]))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many executions since *since* landed in each status."""
        stmt = (
            select(JobExecution.status, func.count())
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.queued_at >= since)
            .group_by(JobExecution.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[JobExecution]:
        """Executions queued within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(JobExecution.organization_id == organization_id)
            .where(JobExecution.queued_at >= start)
            .where(JobExecution.queued_at < end)
            .order_by(JobExecution.queued_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class JobExecutionLogRepository(BaseRepository[JobExecutionLog]):
    """Log lines belonging to one execution."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobExecutionLog, tenant_scope=tenant_scope)

    async def list_for_execution(
        self, organization_id: UUID, execution_id: UUID, *, limit: int = 2_000
    ) -> list[JobExecutionLog]:
        """Every log line for one execution, oldest first."""
        stmt = (
            self._base_select()
            .where(JobExecutionLog.organization_id == organization_id)
            .where(JobExecutionLog.execution_id == execution_id)
            .order_by(JobExecutionLog.occurred_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["JobExecutionLogRepository", "JobExecutionRepository"]
