"""Repository for :class:`app.models.execution.AgentExecution`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import AgentExecution


class AgentExecutionRepository(BaseRepository[AgentExecution]):
    """CRUD plus lookup for :class:`AgentExecution`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentExecution, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, execution_id: UUID) -> AgentExecution:
        """Return *execution_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such execution exists in that organization.
        """
        stmt = self._base_select().where(
            AgentExecution.id == execution_id, AgentExecution.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentExecution {execution_id!s} was not found in organization "
                f"{organization_id!s}."
            )
        return found

    async def list_for_agent(self, agent_id: UUID, *, limit: int = 100) -> list[AgentExecution]:
        """*agent_id*'s own most recent executions, newest first."""
        stmt = (
            self._base_select()
            .where(AgentExecution.agent_id == agent_id)
            .order_by(AgentExecution.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_task(self, task_id: UUID) -> list[AgentExecution]:
        """Every execution recorded against one specific task."""
        stmt = self._base_select().where(AgentExecution.task_id == task_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentExecutionRepository"]
