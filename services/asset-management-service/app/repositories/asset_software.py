"""Repository for :class:`app.models.asset_software.AssetSoftware`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_software import AssetSoftware


class AssetSoftwareRepository(BaseRepository[AssetSoftware]):
    """CRUD plus lookup for :class:`AssetSoftware`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetSoftware, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetSoftware]:
        """Every installed software item on *managed_asset_id*."""
        stmt = self._base_select().where(AssetSoftware.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetSoftwareRepository"]
