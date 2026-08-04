"""The approval-chain repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ChangeApproval
from app.models.enums import ApprovalStatus


class ChangeApprovalRepository(BaseRepository[ChangeApproval]):
    """The approval chain for each change."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeApproval, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, approval_id: UUID) -> ChangeApproval:
        """One approval step by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeApproval.organization_id == organization_id)
            .where(ChangeApproval.id == approval_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeApproval | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No approval step with id {approval_id} in this organization.")
        return found

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeApproval]:
        """Every approval step for one change, ordered by level."""
        stmt = (
            self._base_select()
            .where(ChangeApproval.organization_id == organization_id)
            .where(ChangeApproval.change_id == change_id)
            .order_by(ChangeApproval.level, ChangeApproval.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_expiring_before(
        self, organization_id: UUID, *, before: datetime, limit: int = 200
    ) -> list[ChangeApproval]:
        """Pending approval steps whose expiry has passed, for the expiry sweep."""
        stmt = (
            self._base_select()
            .where(ChangeApproval.organization_id == organization_id)
            .where(ChangeApproval.status == str(ApprovalStatus.PENDING))
            .where(ChangeApproval.expires_at.is_not(None))
            .where(ChangeApproval.expires_at < before)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ChangeApprovalRepository"]
