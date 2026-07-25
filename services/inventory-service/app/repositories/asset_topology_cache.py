"""Repository for :class:`app.models.asset_topology_cache.AssetTopologyCacheEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_topology_cache import AssetTopologyCacheEntry


class AssetTopologyCacheRepository(BaseRepository[AssetTopologyCacheEntry]):
    """CRUD plus lookup for :class:`AssetTopologyCacheEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetTopologyCacheEntry, tenant_scope=tenant_scope)

    async def get_by_query_kind(
        self, asset_id: UUID, query_kind: str
    ) -> AssetTopologyCacheEntry | None:
        """Return the cached result for *(asset_id, query_kind)*, or ``None``."""
        stmt = self._base_select().where(
            AssetTopologyCacheEntry.asset_id == asset_id,
            AssetTopologyCacheEntry.query_kind == query_kind,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetTopologyCacheRepository"]
