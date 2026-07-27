"""Repository for :class:`app.models.workflow_context.WorkflowContextEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_context import WorkflowContextEntry


class WorkflowContextEntryRepository(BaseRepository[WorkflowContextEntry]):
    """CRUD plus lookup for :class:`WorkflowContextEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowContextEntry, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowContextEntry]:
        """Every context entry recorded for *instance_id*."""
        stmt = self._base_select().where(WorkflowContextEntry.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowContextEntryRepository"]
