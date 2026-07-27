"""Repository for :class:`app.models.workflow_replay.WorkflowReplay`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_replay import WorkflowReplay


class WorkflowReplayRepository(BaseRepository[WorkflowReplay]):
    """CRUD plus lookup for :class:`WorkflowReplay`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowReplay, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowReplay]:
        """Every replay recorded for *instance_id*, newest first ("Replay History")."""
        stmt = (
            self._base_select()
            .where(WorkflowReplay.instance_id == instance_id)
            .order_by(desc(WorkflowReplay.requested_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowReplayRepository"]
