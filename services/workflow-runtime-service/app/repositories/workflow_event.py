"""Repository for :class:`app.models.workflow_event.WorkflowEventRecord`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_event import WorkflowEventRecord


class WorkflowEventRecordRepository(BaseRepository[WorkflowEventRecord]):
    """CRUD plus lookup for :class:`WorkflowEventRecord`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowEventRecord, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowEventRecord]:
        """Every event recorded for *instance_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(WorkflowEventRecord.instance_id == instance_id)
            .order_by(asc(WorkflowEventRecord.occurred_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowEventRecordRepository"]
