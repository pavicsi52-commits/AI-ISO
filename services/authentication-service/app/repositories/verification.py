"""Repository for :class:`app.models.email_verification.EmailVerificationToken`."""

from __future__ import annotations

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification import EmailVerificationToken


class EmailVerificationTokenRepository(BaseRepository[EmailVerificationToken]):
    """CRUD plus hash lookup for :class:`EmailVerificationToken`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, EmailVerificationToken, tenant_scope=tenant_scope)

    async def get_by_token_hash(self, token_hash: str) -> EmailVerificationToken | None:
        """Return the verification token row with this hash, or ``None``."""
        stmt = self._base_select().where(EmailVerificationToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["EmailVerificationTokenRepository"]
