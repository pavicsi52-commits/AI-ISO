"""Repository for :class:`app.models.workflow_definition.WorkflowDefinition`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_definition import WorkflowDefinition


class WorkflowDefinitionRepository(BaseRepository[WorkflowDefinition]):
    """CRUD plus lookup for :class:`WorkflowDefinition`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowDefinition, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[WorkflowDefinition]:
        """Every workflow definition belonging to *organization_id*."""
        stmt = self._base_select().where(WorkflowDefinition.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self, organization_id: UUID, workflow_key: str
    ) -> WorkflowDefinition | None:
        """Return *organization_id*'s definition named exactly *workflow_key*, or ``None``."""
        stmt = self._base_select().where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.workflow_key == workflow_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["WorkflowDefinitionRepository"]
