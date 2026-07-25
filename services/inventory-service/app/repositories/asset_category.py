"""Repository for :class:`app.models.asset_category.AssetCategory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_category import AssetCategory


class AssetCategoryRepository(BaseRepository[AssetCategory]):
    """CRUD plus lookup for :class:`AssetCategory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetCategory, tenant_scope=tenant_scope)

    async def get_by_name(self, organization_id: UUID, name: str) -> AssetCategory | None:
        """Return the category identified by *name* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            AssetCategory.organization_id == organization_id, AssetCategory.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[AssetCategory]:
        """Every category defined for *organization_id*."""
        stmt = self._base_select().where(AssetCategory.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetCategoryRepository"]
