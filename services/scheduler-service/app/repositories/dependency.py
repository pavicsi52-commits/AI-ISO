"""The job dependency repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dependency import JobDependency


class JobDependencyRepository(BaseRepository[JobDependency]):
    """Directed edges: *child_job* depends on *parent_job*."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobDependency, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, dependency_id: UUID) -> JobDependency:
        """One dependency edge by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(JobDependency.organization_id == organization_id)
            .where(JobDependency.id == dependency_id)
        )
        result = await self._session.execute(stmt)
        found: JobDependency | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No dependency with id {dependency_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 10_000
    ) -> list[JobDependency]:
        """Every dependency edge in one organization -- for whole-graph cycle/order checks."""
        stmt = (
            self._base_select().where(JobDependency.organization_id == organization_id).limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_parents_of(
        self, organization_id: UUID, child_job_id: UUID
    ) -> list[JobDependency]:
        """Every dependency edge naming *child_job_id* as the dependent side."""
        stmt = (
            self._base_select()
            .where(JobDependency.organization_id == organization_id)
            .where(JobDependency.child_job_id == child_job_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children_of(
        self, organization_id: UUID, parent_job_id: UUID
    ) -> list[JobDependency]:
        """Every dependency edge naming *parent_job_id* as the depended-on side."""
        stmt = (
            self._base_select()
            .where(JobDependency.organization_id == organization_id)
            .where(JobDependency.parent_job_id == parent_job_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["JobDependencyRepository"]
