"""Repositories for job definition history and execution failures."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.history import JobFailure, JobHistory


class JobHistoryRepository(BaseRepository[JobHistory]):
    """A job definition's own status-transition ledger."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobHistory, tenant_scope=tenant_scope)

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, limit: int = 500
    ) -> list[JobHistory]:
        """Every status transition for one job, oldest first."""
        stmt = (
            self._base_select()
            .where(JobHistory.organization_id == organization_id)
            .where(JobHistory.job_id == job_id)
            .order_by(JobHistory.occurred_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class JobFailureRepository(BaseRepository[JobFailure]):
    """One row per execution's failure, and how it was (or wasn't) recovered."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobFailure, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, failure_id: UUID) -> JobFailure:
        """One failure by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(JobFailure.organization_id == organization_id)
            .where(JobFailure.id == failure_id)
        )
        result = await self._session.execute(stmt)
        found: JobFailure | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No failure with id {failure_id} in this organization.")
        return found

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, limit: int = 200
    ) -> list[JobFailure]:
        """Every failure recorded for one job, newest first."""
        stmt = (
            self._base_select()
            .where(JobFailure.organization_id == organization_id)
            .where(JobFailure.job_id == job_id)
            .order_by(JobFailure.occurred_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unrecovered_terminal(
        self, organization_id: UUID, *, limit: int = 500
    ) -> list[JobFailure]:
        """Every terminal (retries-exhausted) failure nobody has recovered yet."""
        stmt = (
            self._base_select()
            .where(JobFailure.organization_id == organization_id)
            .where(JobFailure.is_terminal.is_(True))
            .where(JobFailure.recovered.is_(False))
            .order_by(JobFailure.occurred_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_for_retry(
        self, organization_id: UUID, *, before: datetime, limit: int = 500
    ) -> list[JobFailure]:
        """Every non-terminal, not-yet-retried failure whose ``retry_at`` has arrived."""
        stmt = (
            self._base_select()
            .where(JobFailure.organization_id == organization_id)
            .where(JobFailure.is_terminal.is_(False))
            .where(JobFailure.retried.is_(False))
            .where(JobFailure.retry_at.is_not(None))
            .where(JobFailure.retry_at <= before)
            .order_by(JobFailure.retry_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["JobFailureRepository", "JobHistoryRepository"]
