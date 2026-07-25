"""Repository for :class:`app.models.tag.UserTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import UserTag


class UserTagRepository(BaseRepository[UserTag]):
    """CRUD plus listing/lookup for :class:`UserTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserTag, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[UserTag]:
        """Every tag assigned to *user_id*."""
        stmt = self._base_select().where(UserTag.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_label(self, user_id: UUID, label: str) -> UserTag | None:
        """Return *user_id*'s tag matching *label*, or ``None``."""
        stmt = self._base_select().where(UserTag.user_id == user_id, UserTag.label == label)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users_for_label(self, label: str) -> list[UserTag]:
        """Every tag assignment matching *label*, across all users ("Filtering" by tag)."""
        stmt = self._base_select().where(UserTag.label == label)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserTagRepository"]
