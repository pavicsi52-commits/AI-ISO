"""Repositories for :class:`app.models.password.PasswordHistoryEntry` and
:class:`app.models.password.PasswordResetToken`.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password import PasswordHistoryEntry, PasswordResetToken


class PasswordHistoryRepository(BaseRepository[PasswordHistoryEntry]):
    """CRUD plus recent-history listing for :class:`PasswordHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PasswordHistoryEntry, tenant_scope=tenant_scope)

    async def list_recent_for_user(
        self, user_id: UUID, *, limit: int
    ) -> list[PasswordHistoryEntry]:
        """The *limit* most recent password hashes for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(PasswordHistoryEntry.user_id == user_id)
            .order_by(desc(PasswordHistoryEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    """CRUD plus hash lookup for :class:`PasswordResetToken`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PasswordResetToken, tenant_scope=tenant_scope)

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Return the reset token row with this hash, or ``None``."""
        stmt = self._base_select().where(PasswordResetToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["PasswordHistoryRepository", "PasswordResetTokenRepository"]
