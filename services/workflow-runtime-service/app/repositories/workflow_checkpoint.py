"""Repository for :class:`app.models.workflow_checkpoint.WorkflowCheckpoint`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_checkpoint import WorkflowCheckpoint


class WorkflowCheckpointRepository(BaseRepository[WorkflowCheckpoint]):
    """CRUD plus lookup for :class:`WorkflowCheckpoint`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowCheckpoint, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowCheckpoint]:
        """Every checkpoint recorded for *instance_id*, newest first."""
        stmt = (
            self._base_select()
            .where(WorkflowCheckpoint.instance_id == instance_id)
            .order_by(desc(WorkflowCheckpoint.checkpointed_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_instance(self, instance_id: UUID) -> WorkflowCheckpoint | None:
        """Return *instance_id*'s most recently recorded checkpoint, or ``None``."""
        stmt = (
            self._base_select()
            .where(WorkflowCheckpoint.instance_id == instance_id)
            .order_by(desc(WorkflowCheckpoint.checkpointed_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["WorkflowCheckpointRepository"]
