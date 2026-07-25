"""Repository for :class:`app.models.metadata.UserMetadataEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata import UserMetadataEntry


class UserMetadataRepository(BaseRepository[UserMetadataEntry]):
    """CRUD plus per-user key lookup/listing for :class:`UserMetadataEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserMetadataEntry, tenant_scope=tenant_scope)

    async def get_by_key(self, user_id: UUID, key: str) -> UserMetadataEntry | None:
        """Return *user_id*'s metadata entry for *key*, or ``None``."""
        stmt = self._base_select().where(
            UserMetadataEntry.user_id == user_id, UserMetadataEntry.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[UserMetadataEntry]:
        """Every metadata entry on record for *user_id*."""
        stmt = self._base_select().where(UserMetadataEntry.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserMetadataRepository"]
