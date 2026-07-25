"""Repository for :class:`app.models.api_key.ApiKeyEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKeyEntry


class ApiKeyRepository(BaseRepository[ApiKeyEntry]):
    """CRUD plus lookup for :class:`ApiKeyEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiKeyEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ApiKeyEntry]:
        """Every managed API key belonging to *organization_id*."""
        stmt = self._base_select().where(ApiKeyEntry.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ApiKeyRepository"]
