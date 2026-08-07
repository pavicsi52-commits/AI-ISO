"""Repository for :class:`app.models.task.AgentTask`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import AgentTask


class AgentTaskRepository(BaseRepository[AgentTask]):
    """CRUD plus lookup for :class:`AgentTask`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentTask, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, task_id: UUID) -> AgentTask:
        """Return *task_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such task exists in that organization.
        """
        stmt = self._base_select().where(
            AgentTask.id == task_id, AgentTask.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentTask {task_id!s} was not found in organization {organization_id!s}."
            )
        return found

    async def list_due(self, moment: datetime, *, limit: int = 100) -> list[AgentTask]:
        """Every ``PENDING``/``QUEUED`` task whose own ``scheduled_at``
        has arrived, oldest first -- backs the task dispatch sweep.
        """
        stmt = (
            self._base_select()
            .where(
                AgentTask.status.in_((TaskStatus.PENDING, TaskStatus.QUEUED)),
                AgentTask.scheduled_at <= moment,
            )
            .order_by(AgentTask.scheduled_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self, parent_task_id: UUID) -> list[AgentTask]:
        """Every task whose own ``parent_task_id`` is *parent_task_id*
        ("Dependencies")."""
        stmt = self._base_select().where(AgentTask.parent_task_id == parent_task_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_agent(self, agent_id: UUID) -> list[AgentTask]:
        """Every task assigned to *agent_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AgentTask.agent_id == agent_id)
            .order_by(AgentTask.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentTaskRepository"]
