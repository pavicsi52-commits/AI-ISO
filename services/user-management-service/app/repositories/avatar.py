"""Repository for :class:`app.models.avatar.UserAvatar`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.avatar import UserAvatar


class UserAvatarRepository(BaseRepository[UserAvatar]):
    """CRUD plus current-avatar lookup/history for :class:`UserAvatar`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserAvatar, tenant_scope=tenant_scope)

    async def get_current_for_user(self, user_id: UUID) -> UserAvatar | None:
        """Return *user_id*'s current avatar row, or ``None``."""
        stmt = self._base_select().where(
            UserAvatar.user_id == user_id, UserAvatar.is_current.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_history_for_user(self, user_id: UUID, *, limit: int = 20) -> list[UserAvatar]:
        """*limit* most recent avatar uploads for *user_id*, newest first."""
        stmt = (
            self._base_select()
            .where(UserAvatar.user_id == user_id)
            .order_by(desc(UserAvatar.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserAvatarRepository"]
