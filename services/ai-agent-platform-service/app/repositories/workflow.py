"""Repository for :class:`app.models.workflow.AgentWorkflow`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowRunStatus
from app.models.workflow import AgentWorkflow


class AgentWorkflowRepository(BaseRepository[AgentWorkflow]):
    """CRUD plus lookup for :class:`AgentWorkflow`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentWorkflow, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, workflow_id: UUID) -> AgentWorkflow:
        """Return *workflow_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such workflow exists in that organization.
        """
        stmt = self._base_select().where(
            AgentWorkflow.id == workflow_id, AgentWorkflow.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        workflow: AgentWorkflow | None = result.scalars().first()
        if workflow is None:
            raise NotFoundError(
                f"AgentWorkflow {workflow_id!s} was not found in organization {organization_id!s}."
            )
        return workflow

    async def list_for_agent(self, agent_id: UUID) -> list[AgentWorkflow]:
        """Every workflow run belonging to *agent_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AgentWorkflow.agent_id == agent_id)
            .order_by(AgentWorkflow.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_stuck_running(
        self, cutoff: datetime, *, limit: int = 100
    ) -> list[AgentWorkflow]:
        """Every workflow still ``RUNNING`` whose own ``started_at`` is
        older than *cutoff* -- a real crash-recovery signal: a run
        genuinely still in progress keeps advancing its own checkpoint
        on every level, so one stuck this long almost certainly died
        mid-run rather than merely being slow. Backs the checkpoint
        recovery sweep, which resumes each one from its own last
        persisted checkpoint.
        """
        stmt = (
            self._base_select()
            .where(
                AgentWorkflow.status == WorkflowRunStatus.RUNNING,
                AgentWorkflow.started_at.is_not(None),
                AgentWorkflow.started_at <= cutoff,
            )
            .order_by(AgentWorkflow.started_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentWorkflowRepository"]
