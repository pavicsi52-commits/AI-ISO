"""Repository for :class:`app.models.workflow_audit.WorkflowAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_audit import WorkflowAuditEntry


class WorkflowAuditEntryRepository(BaseRepository[WorkflowAuditEntry]):
    """CRUD plus lookup for :class:`WorkflowAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowAuditEntry, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowAuditEntry]:
        """Every audit entry recorded against *instance_id*."""
        stmt = self._base_select().where(WorkflowAuditEntry.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowAuditEntryRepository"]
