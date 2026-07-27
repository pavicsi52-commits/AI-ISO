"""Repository for :class:`app.models.workflow_instance.WorkflowInstance`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_instance import WorkflowInstance


class WorkflowInstanceRepository(BaseRepository[WorkflowInstance]):
    """CRUD plus lookup for :class:`WorkflowInstance`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowInstance, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, status: WorkflowInstanceStatus | None = None
    ) -> list[WorkflowInstance]:
        """Every instance belonging to *organization_id*, newest first,
        optionally narrowed to a single *status*.
        """
        stmt = self._base_select().where(WorkflowInstance.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(WorkflowInstance.status == status)
        stmt = stmt.order_by(desc(WorkflowInstance.created_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowInstance]:
        """Every instance run of *definition_id*, newest first."""
        stmt = (
            self._base_select()
            .where(WorkflowInstance.definition_id == definition_id)
            .order_by(desc(WorkflowInstance.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self, parent_instance_id: UUID) -> list[WorkflowInstance]:
        """Every child instance a ``SUB_WORKFLOW`` node spawned from *parent_instance_id*."""
        stmt = self._base_select().where(WorkflowInstance.parent_instance_id == parent_instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowInstanceRepository"]
