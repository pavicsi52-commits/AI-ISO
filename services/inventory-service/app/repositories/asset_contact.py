"""Repository for :class:`app.models.asset_contact.AssetContact`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_contact import AssetContact


class AssetContactRepository(BaseRepository[AssetContact]):
    """CRUD plus lookup for :class:`AssetContact`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetContact, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetContact]:
        """Every contact person associated with *asset_id*."""
        stmt = self._base_select().where(AssetContact.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetContactRepository"]
