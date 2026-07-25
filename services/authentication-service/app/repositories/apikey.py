"""Repository for :class:`app.models.apikey.ApiKey`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apikey import ApiKey


class ApiKeyRepository(BaseRepository[ApiKey]):
    """CRUD plus lookup/listing for :class:`ApiKey`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiKey, tenant_scope=tenant_scope)

    async def get_by_hashed_key(self, hashed_key: str) -> ApiKey | None:
        """Return the API key row with this hashed key value, or ``None``."""
        stmt = self._base_select().where(ApiKey.hashed_key == hashed_key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        """Every API key belonging to *user_id* ("GET /auth/apikeys")."""
        stmt = self._base_select().where(ApiKey.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiKeyRepository"]
