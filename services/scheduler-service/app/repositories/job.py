"""The scheduled job repository.

Every read is scoped by ``organization_id``. ``require_in_org`` is named
apart from the base repository's unscoped ``require_by_id``, per this
repository's established convention: two same-named methods of different
arity on one class make an unscoped call look correct.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobPriority, JobType, ScheduledJobStatus
from app.models.job import ScheduledJob


class ScheduledJobRepository(BaseRepository[ScheduledJob]):
    """The job catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ScheduledJob, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, job_id: UUID) -> ScheduledJob:
        """One job by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. Deliberately not a
                permission error -- telling a caller it exists but
                belongs to someone else confirms the id, which is the
                one thing they did not already know.
        """
        stmt = (
            self._base_select()
            .where(ScheduledJob.organization_id == organization_id)
            .where(ScheduledJob.id == job_id)
        )
        result = await self._session.execute(stmt)
        found: ScheduledJob | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No job with id {job_id} in this organization.")
        return found

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ScheduledJobStatus | None = None,
        job_type: JobType | None = None,
        priority: JobPriority | None = None,
        owner_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ScheduledJob]:
        """Jobs matching a caller's filters, newest first."""
        stmt = self._base_select().where(ScheduledJob.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ScheduledJob.status == str(status))
        if job_type is not None:
            stmt = stmt.where(ScheduledJob.job_type == str(job_type))
        if priority is not None:
            stmt = stmt.where(ScheduledJob.priority == str(priority))
        if owner_id is not None:
            stmt = stmt.where(ScheduledJob.owner_id == owner_id)
        stmt = stmt.order_by(ScheduledJob.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, organization_id: UUID, *, limit: int = 1_000) -> list[ScheduledJob]:
        """Every job eligible to run -- ``ACTIVE`` status."""
        stmt = (
            self._base_select()
            .where(ScheduledJob.organization_id == organization_id)
            .where(ScheduledJob.status == str(ScheduledJobStatus.ACTIVE))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many jobs sit in each definition status."""
        stmt = (
            select(ScheduledJob.status, func.count())
            .where(ScheduledJob.organization_id == organization_id)
            .where(ScheduledJob.deleted_at.is_(None))
            .group_by(ScheduledJob.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[ScheduledJob]:
        """Jobs created within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(ScheduledJob.organization_id == organization_id)
            .where(ScheduledJob.created_at >= start)
            .where(ScheduledJob.created_at < end)
            .order_by(ScheduledJob.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ScheduledJobRepository"]
