"""Repository for :class:`app.models.asset_depreciation.AssetDepreciation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_depreciation import AssetDepreciation


class AssetDepreciationRepository(BaseRepository[AssetDepreciation]):
    """CRUD plus lookup for :class:`AssetDepreciation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetDepreciation, tenant_scope=tenant_scope)

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetDepreciation | None:
        """Return *managed_asset_id*'s depreciation record, or ``None``."""
        stmt = self._base_select().where(AssetDepreciation.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetDepreciationRepository"]
