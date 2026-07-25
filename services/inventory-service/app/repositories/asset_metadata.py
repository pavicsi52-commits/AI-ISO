"""Repository for :class:`app.models.asset_metadata.AssetMetadataEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_metadata import AssetMetadataEntry


class AssetMetadataRepository(BaseRepository[AssetMetadataEntry]):
    """CRUD plus lookup for :class:`AssetMetadataEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetMetadataEntry, tenant_scope=tenant_scope)

    async def get_by_key(self, asset_id: UUID, key: str) -> AssetMetadataEntry | None:
        """Return the metadata entry identified by *key* on *asset_id*, or ``None``."""
        stmt = self._base_select().where(
            AssetMetadataEntry.asset_id == asset_id, AssetMetadataEntry.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetMetadataEntry]:
        """Every metadata entry for *asset_id*."""
        stmt = self._base_select().where(AssetMetadataEntry.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetMetadataRepository"]
