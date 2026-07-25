"""Repository for :class:`app.models.asset_discovery_link.AssetDiscoveryLink`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_discovery_link import AssetDiscoveryLink
from app.models.enums import DiscoverySource


class AssetDiscoveryLinkRepository(BaseRepository[AssetDiscoveryLink]):
    """CRUD plus lookup for :class:`AssetDiscoveryLink`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetDiscoveryLink, tenant_scope=tenant_scope)

    async def get_by_external_id(
        self, source: DiscoverySource, external_id: str
    ) -> AssetDiscoveryLink | None:
        """Return the link identified by *(source, external_id)*, or ``None``."""
        stmt = self._base_select().where(
            AssetDiscoveryLink.source == source, AssetDiscoveryLink.external_id == external_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetDiscoveryLink]:
        """Every discovery correlation recorded for *asset_id*."""
        stmt = self._base_select().where(AssetDiscoveryLink.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetDiscoveryLinkRepository"]
