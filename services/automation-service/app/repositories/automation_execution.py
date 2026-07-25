"""Repository for :class:`app.models.automation_execution.AutomationExecution`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.enums import ExecutionStatus

_ACTIVE_STATUSES = (ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.PAUSED)


class AutomationExecutionRepository(BaseRepository[AutomationExecution]):
    """CRUD plus lookup for :class:`AutomationExecution`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationExecution, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[AutomationExecution]:
        """Every execution recorded for *job_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AutomationExecution.job_id == job_id)
            .order_by(desc(AutomationExecution.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(
        self, organization_id: UUID, *, status: ExecutionStatus | None = None
    ) -> list[AutomationExecution]:
        """Every execution for *organization_id*, newest first, optionally
        narrowed to a single *status*.
        """
        stmt = self._base_select().where(AutomationExecution.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(AutomationExecution.status == status)
        stmt = stmt.order_by(desc(AutomationExecution.created_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_org(self, organization_id: UUID) -> list[AutomationExecution]:
        """Every not-yet-finished execution for *organization_id*."""
        stmt = self._base_select().where(
            AutomationExecution.organization_id == organization_id,
            AutomationExecution.status.in_(_ACTIVE_STATUSES),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationExecutionRepository"]
