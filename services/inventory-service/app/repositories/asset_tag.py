"""Repository for :class:`app.models.asset_tag.AssetTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_tag import AssetTag


class AssetTagRepository(BaseRepository[AssetTag]):
    """CRUD plus lookup for :class:`AssetTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetTag, tenant_scope=tenant_scope)

    async def get_by_label(self, asset_id: UUID, label: str) -> AssetTag | None:
        """Return the tag identified by *label* on *asset_id*, or ``None``."""
        stmt = self._base_select().where(AssetTag.asset_id == asset_id, AssetTag.label == label)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetTag]:
        """Every tag assigned to *asset_id*."""
        stmt = self._base_select().where(AssetTag.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetTagRepository"]
