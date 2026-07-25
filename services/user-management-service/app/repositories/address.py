"""Repository for :class:`app.models.address.UserAddress`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import UserAddress


class UserAddressRepository(BaseRepository[UserAddress]):
    """CRUD plus listing for :class:`UserAddress`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, UserAddress, tenant_scope=tenant_scope)

    async def list_for_user(self, user_id: UUID) -> list[UserAddress]:
        """Every address on record for *user_id*."""
        stmt = self._base_select().where(UserAddress.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["UserAddressRepository"]
