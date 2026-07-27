"""Repository for :class:`app.models.workflow_result.WorkflowResult`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_result import WorkflowResult


class WorkflowResultRepository(BaseRepository[WorkflowResult]):
    """CRUD plus lookup for :class:`WorkflowResult`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowResult, tenant_scope=tenant_scope)

    async def get_for_instance(self, instance_id: UUID) -> WorkflowResult | None:
        """Return *instance_id*'s own final outcome, or ``None`` if not yet finished."""
        stmt = self._base_select().where(WorkflowResult.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["WorkflowResultRepository"]
