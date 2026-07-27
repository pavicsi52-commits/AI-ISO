"""Repository for :class:`app.models.playbook_approval.PlaybookApproval`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalStatus
from app.models.playbook_approval import PlaybookApproval


class PlaybookApprovalRepository(BaseRepository[PlaybookApproval]):
    """CRUD plus lookup for :class:`PlaybookApproval`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookApproval, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookApproval]:
        """Every approval step recorded for *playbook_id*."""
        stmt = self._base_select().where(PlaybookApproval.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_org(self, organization_id: UUID) -> list[PlaybookApproval]:
        """Every still-pending approval for *organization_id*."""
        stmt = self._base_select().where(
            PlaybookApproval.organization_id == organization_id,
            PlaybookApproval.status == ApprovalStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookApprovalRepository"]
