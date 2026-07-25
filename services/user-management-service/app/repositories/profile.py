"""Repository for :class:`app.models.profile.UserProfile`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import UserProfile


class UserProfileRepository(BaseRepository[UserProfile]):
    """CRUD plus per-user lookup for :class:`UserProfile`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserProfile, tenant_scope=tenant_scope)

    async def get_for_user(self, user_id: UUID) -> UserProfile | None:
        """Return *user_id*'s profile row, or ``None``."""
        stmt = self._base_select().where(UserProfile.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["UserProfileRepository"]
