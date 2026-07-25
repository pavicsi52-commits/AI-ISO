"""Repository for :class:`app.models.asset_vendor.AssetVendor`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_vendor import AssetVendor


class AssetVendorRepository(BaseRepository[AssetVendor]):
    """CRUD plus lookup for :class:`AssetVendor`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetVendor, tenant_scope=tenant_scope)

    async def get_by_name(self, organization_id: UUID, name: str) -> AssetVendor | None:
        """Return *organization_id*'s vendor named *name*, or ``None``."""
        stmt = self._base_select().where(
            AssetVendor.organization_id == organization_id, AssetVendor.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[AssetVendor]:
        """Every vendor registered for *organization_id*."""
        stmt = self._base_select().where(AssetVendor.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetVendorRepository"]
