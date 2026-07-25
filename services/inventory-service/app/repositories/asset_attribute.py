"""Repository for :class:`app.models.asset_attribute.AssetAttribute`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_attribute import AssetAttribute


class AssetAttributeRepository(BaseRepository[AssetAttribute]):
    """CRUD plus lookup for :class:`AssetAttribute`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetAttribute, tenant_scope=tenant_scope)

    async def get_for_field(self, asset_id: UUID, custom_field_id: UUID) -> AssetAttribute | None:
        """Return *asset_id*'s value for *custom_field_id*, or ``None``."""
        stmt = self._base_select().where(
            AssetAttribute.asset_id == asset_id,
            AssetAttribute.custom_field_id == custom_field_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetAttribute]:
        """Every custom attribute value set on *asset_id*."""
        stmt = self._base_select().where(AssetAttribute.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetAttributeRepository"]
