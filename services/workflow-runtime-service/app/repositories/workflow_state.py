"""Repository for :class:`app.models.workflow_state.WorkflowStateTransition`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_state import WorkflowStateTransition


class WorkflowStateTransitionRepository(BaseRepository[WorkflowStateTransition]):
    """CRUD plus lookup for :class:`WorkflowStateTransition`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowStateTransition, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowStateTransition]:
        """Every state transition recorded for *instance_id*, oldest first ("State Changes")."""
        stmt = (
            self._base_select()
            .where(WorkflowStateTransition.instance_id == instance_id)
            .order_by(asc(WorkflowStateTransition.transitioned_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowStateTransitionRepository"]
