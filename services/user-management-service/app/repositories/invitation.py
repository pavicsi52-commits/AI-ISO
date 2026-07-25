"""Repository for :class:`app.models.invitation.UserInvitation`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InvitationStatus
from app.models.invitation import UserInvitation


class UserInvitationRepository(BaseRepository[UserInvitation]):
    """CRUD plus lookup/listing for :class:`UserInvitation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserInvitation, tenant_scope=tenant_scope)

    async def get_by_token_hash(self, token_hash: str) -> UserInvitation | None:
        """Return the invitation with this token hash, or ``None``."""
        stmt = self._base_select().where(UserInvitation.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_for_email(self, email: str) -> UserInvitation | None:
        """Return *email*'s currently-pending invitation, or ``None``."""
        stmt = self._base_select().where(
            UserInvitation.email == email, UserInvitation.status == InvitationStatus.PENDING
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending(self, *, limit: int = 100) -> list[UserInvitation]:
        """The *limit* most recently-created pending invitations."""
        stmt = (
            self._base_select()
            .where(UserInvitation.status == InvitationStatus.PENDING)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserInvitationRepository"]
