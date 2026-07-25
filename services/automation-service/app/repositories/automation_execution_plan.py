"""Repository for :class:`app.models.automation_execution_plan.AutomationExecutionPlan`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution_plan import AutomationExecutionPlan


class AutomationExecutionPlanRepository(BaseRepository[AutomationExecutionPlan]):
    """CRUD plus lookup for :class:`AutomationExecutionPlan`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationExecutionPlan, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AutomationExecutionPlan]:
        """Every execution plan belonging to *organization_id*."""
        stmt = self._base_select().where(AutomationExecutionPlan.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID) -> list[AutomationExecutionPlan]:
        """Every execution plan attached to *job_id*."""
        stmt = self._base_select().where(AutomationExecutionPlan.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationExecutionPlanRepository"]
