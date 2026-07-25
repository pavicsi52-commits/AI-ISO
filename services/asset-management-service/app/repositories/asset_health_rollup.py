"""Repository for :class:`app.models.asset_health_rollup.AssetHealthRollup`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_health_rollup import AssetHealthRollup


class AssetHealthRollupRepository(BaseRepository[AssetHealthRollup]):
    """CRUD plus lookup for :class:`AssetHealthRollup`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetHealthRollup, tenant_scope=tenant_scope)

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetHealthRollup | None:
        """Return *managed_asset_id*'s cached health rollup, or ``None``."""
        stmt = self._base_select().where(AssetHealthRollup.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetHealthRollupRepository"]
