"""Repository for :class:`app.models.contact.UserContact`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import UserContact


class UserContactRepository(BaseRepository[UserContact]):
    """CRUD plus listing for :class:`UserContact`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserContact, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[UserContact]:
        """Every additional contact method on record for *user_id*."""
        stmt = self._base_select().where(UserContact.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserContactRepository"]
