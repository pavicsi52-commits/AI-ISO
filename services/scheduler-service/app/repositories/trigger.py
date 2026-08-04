"""Repositories for job triggers and each job's materialized schedule state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trigger import JobSchedule, JobTrigger


class JobTriggerRepository(BaseRepository[JobTrigger]):
    """Declarative trigger rules -- a job may have more than one."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobTrigger, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, trigger_id: UUID) -> JobTrigger:
        """One trigger by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(JobTrigger.organization_id == organization_id)
            .where(JobTrigger.id == trigger_id)
        )
        result = await self._session.execute(stmt)
        found: JobTrigger | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No trigger with id {trigger_id} in this organization.")
        return found

    async def list_for_job(self, organization_id: UUID, job_id: UUID) -> list[JobTrigger]:
        """Every trigger registered for one job."""
        stmt = (
            self._base_select()
            .where(JobTrigger.organization_id == organization_id)
            .where(JobTrigger.job_id == job_id)
            .order_by(JobTrigger.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_job(self, organization_id: UUID, job_id: UUID) -> list[JobTrigger]:
        """Every currently-enabled trigger for one job."""
        stmt = (
            self._base_select()
            .where(JobTrigger.organization_id == organization_id)
            .where(JobTrigger.job_id == job_id)
            .where(JobTrigger.enabled.is_(True))
            .order_by(JobTrigger.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class JobScheduleRepository(BaseRepository[JobSchedule]):
    """One materialized next-due row per job."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobSchedule, tenant_scope=tenant_scope)

    async def get_for_job(self, organization_id: UUID, job_id: UUID) -> JobSchedule | None:
        """The materialized schedule state for one job, if it has been computed."""
        stmt = (
            self._base_select()
            .where(JobSchedule.organization_id == organization_id)
            .where(JobSchedule.job_id == job_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def require_for_job(self, organization_id: UUID, job_id: UUID) -> JobSchedule:
        """The materialized schedule state for one job.

        Raises:
            NotFoundError: If it has never been computed for this job.
        """
        found = await self.get_for_job(organization_id, job_id)
        if found is None:
            raise NotFoundError(f"No schedule state exists yet for job {job_id}.")
        return found

    async def list_due(
        self, organization_id: UUID, *, before: datetime, limit: int = 500
    ) -> list[JobSchedule]:
        """Every job schedule whose ``next_run_at`` has arrived, not currently paused."""
        stmt = (
            self._base_select()
            .where(JobSchedule.organization_id == organization_id)
            .where(JobSchedule.is_paused.is_(False))
            .where(JobSchedule.next_run_at.is_not(None))
            .where(JobSchedule.next_run_at <= before)
            .order_by(JobSchedule.next_run_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["JobScheduleRepository", "JobTriggerRepository"]
