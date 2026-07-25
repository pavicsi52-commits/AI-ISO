"""Repository for :class:`app.models.settings.UserSettings`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import UserSettings


class UserSettingsRepository(BaseRepository[UserSettings]):
    """CRUD plus per-user lookup for :class:`UserSettings`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserSettings, tenant_scope=tenant_scope)

    async def get_for_user(self, user_id: UUID) -> UserSettings | None:
        """Return *user_id*'s settings row, or ``None``."""
        stmt = self._base_select().where(UserSettings.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["UserSettingsRepository"]
