"""Repository for :class:`app.models.automation_approval.AutomationApproval`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_approval import AutomationApproval
from app.models.enums import ApprovalStatus


class AutomationApprovalRepository(BaseRepository[AutomationApproval]):
    """CRUD plus lookup for :class:`AutomationApproval`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationApproval, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationApproval]:
        """Every approval step recorded for *execution_id*."""
        stmt = self._base_select().where(AutomationApproval.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_org(self, organization_id: UUID) -> list[AutomationApproval]:
        """Every still-pending approval for *organization_id*."""
        stmt = self._base_select().where(
            AutomationApproval.organization_id == organization_id,
            AutomationApproval.status == ApprovalStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationApprovalRepository"]
