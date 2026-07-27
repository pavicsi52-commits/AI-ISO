"""Repository for :class:`app.models.workflow_variable.WorkflowVariable`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_variable import WorkflowVariable


class WorkflowVariableRepository(BaseRepository[WorkflowVariable]):
    """CRUD plus lookup for :class:`WorkflowVariable`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowVariable, tenant_scope=tenant_scope)

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowVariable]:
        """Every definition-level default variable (``instance_id IS NULL``)."""
        stmt = self._base_select().where(
            WorkflowVariable.definition_id == definition_id,
            WorkflowVariable.instance_id.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowVariable]:
        """Every resolved runtime variable recorded for *instance_id*."""
        stmt = self._base_select().where(WorkflowVariable.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowVariableRepository"]
