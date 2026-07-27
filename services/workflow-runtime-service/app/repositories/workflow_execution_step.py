"""Repository for :class:`app.models.workflow_execution_step.WorkflowExecutionStep`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_execution_step import WorkflowExecutionStep


class WorkflowExecutionStepRepository(BaseRepository[WorkflowExecutionStep]):
    """CRUD plus lookup for :class:`WorkflowExecutionStep`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowExecutionStep, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowExecutionStep]:
        """Every node execution result recorded for *instance_id*."""
        stmt = self._base_select().where(WorkflowExecutionStep.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_node(self, instance_id: UUID, node_id: str) -> WorkflowExecutionStep | None:
        """Return *instance_id*'s own result for *node_id*, or ``None``."""
        stmt = self._base_select().where(
            WorkflowExecutionStep.instance_id == instance_id,
            WorkflowExecutionStep.node_id == node_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["WorkflowExecutionStepRepository"]
