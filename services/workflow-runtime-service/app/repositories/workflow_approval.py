"""Repository for :class:`app.models.workflow_approval.WorkflowApproval`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalDecisionStatus
from app.models.workflow_approval import WorkflowApproval


class WorkflowApprovalRepository(BaseRepository[WorkflowApproval]):
    """CRUD plus lookup for :class:`WorkflowApproval`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowApproval, tenant_scope=tenant_scope)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowApproval]:
        """Every approval gate recorded for *instance_id* ("Approval History")."""
        stmt = self._base_select().where(WorkflowApproval.instance_id == instance_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_node(self, instance_id: UUID, node_id: str) -> WorkflowApproval | None:
        """Return *instance_id*'s own approval gate for *node_id*, or ``None``."""
        stmt = self._base_select().where(
            WorkflowApproval.instance_id == instance_id, WorkflowApproval.node_id == node_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending_for_org(self, organization_id: UUID) -> list[WorkflowApproval]:
        """Every still-pending approval for *organization_id*."""
        stmt = self._base_select().where(
            WorkflowApproval.organization_id == organization_id,
            WorkflowApproval.decision == ApprovalDecisionStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowApprovalRepository"]
