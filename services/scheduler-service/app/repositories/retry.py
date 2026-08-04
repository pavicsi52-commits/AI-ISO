"""The job retry policy repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retry import JobRetryPolicy


class JobRetryPolicyRepository(BaseRepository[JobRetryPolicy]):
    """One job's own retry configuration, if it overrides the platform default."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobRetryPolicy, tenant_scope=tenant_scope)

    async def get_for_job(self, organization_id: UUID, job_id: UUID) -> JobRetryPolicy | None:
        """This job's own retry policy, if one has been configured."""
        stmt = (
            self._base_select()
            .where(JobRetryPolicy.organization_id == organization_id)
            .where(JobRetryPolicy.job_id == job_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["JobRetryPolicyRepository"]
