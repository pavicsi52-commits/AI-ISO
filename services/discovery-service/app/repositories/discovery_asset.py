"""Repository for :class:`app.models.discovery_asset.DiscoveryAsset`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_asset import DiscoveryAsset


class DiscoveryAssetRepository(BaseRepository[DiscoveryAsset]):
    """CRUD plus lookup for :class:`DiscoveryAsset`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryAsset, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryAsset]:
        """Every discovered asset for *organization_id*."""
        stmt = self._base_select().where(DiscoveryAsset.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryAsset]:
        """Every asset discovered by *job_id*."""
        stmt = self._base_select().where(DiscoveryAsset.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryAssetRepository"]
