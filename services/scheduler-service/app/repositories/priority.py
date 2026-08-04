"""The job priority escalation policy repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobPriority
from app.models.priority import JobPriorityPolicy


class JobPriorityPolicyRepository(BaseRepository[JobPriorityPolicy]):
    """An organization's own escalation rule, one row per priority band."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, JobPriorityPolicy, tenant_scope=tenant_scope)

    async def get_for_priority(
        self, organization_id: UUID, priority: JobPriority
    ) -> JobPriorityPolicy | None:
        """This organization's escalation policy for one band, if configured."""
        stmt = (
            self._base_select()
            .where(JobPriorityPolicy.organization_id == organization_id)
            .where(JobPriorityPolicy.priority == str(priority))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 10
    ) -> list[JobPriorityPolicy]:
        """Every priority band this organization has configured."""
        stmt = (
            self._base_select()
            .where(JobPriorityPolicy.organization_id == organization_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["JobPriorityPolicyRepository"]
