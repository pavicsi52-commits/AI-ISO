"""Repository for :class:`app.models.workflow_compensation.WorkflowCompensation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_compensation import WorkflowCompensation


class WorkflowCompensationRepository(BaseRepository[WorkflowCompensation]):
    """CRUD plus lookup for :class:`WorkflowCompensation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowCompensation, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowCompensation]:
        """Every compensation action recorded for *instance_id* ("Compensation Audit")."""
        stmt = self._base_select().where(WorkflowCompensation.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowCompensationRepository"]
