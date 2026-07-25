"""Repository for :class:`app.models.invitation.OrganizationInvitation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InvitationStatus
from app.models.invitation import OrganizationInvitation


class OrganizationInvitationRepository(BaseRepository[OrganizationInvitation]):
    """CRUD plus lookup for :class:`OrganizationInvitation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationInvitation, tenant_scope=tenant_scope)

    async def get_by_token_hash(self, token_hash: str) -> OrganizationInvitation | None:
        """Return the invitation identified by *token_hash*, or ``None``."""
        stmt = self._base_select().where(OrganizationInvitation.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_for_email(
        self, organization_id: UUID, email: str
    ) -> OrganizationInvitation | None:
        """Return *email*'s pending invitation to *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending(self, organization_id: UUID) -> list[OrganizationInvitation]:
        """Every pending invitation for *organization_id*."""
        stmt = self._base_select().where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["OrganizationInvitationRepository"]
