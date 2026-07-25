"""Repository for :class:`app.models.asset_location.AssetLocation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_location import AssetLocation


class AssetLocationRepository(BaseRepository[AssetLocation]):
    """CRUD plus lookup for :class:`AssetLocation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetLocation, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AssetLocation]:
        """Every location defined for *organization_id*."""
        stmt = self._base_select().where(AssetLocation.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetLocationRepository"]
