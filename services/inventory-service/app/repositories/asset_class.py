"""Repository for :class:`app.models.asset_class.AssetClass`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass


class AssetClassRepository(BaseRepository[AssetClass]):
    """CRUD plus lookup for :class:`AssetClass`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetClass, tenant_scope=tenant_scope)

    async def get_by_name(self, category_id: UUID, name: str) -> AssetClass | None:
        """Return the class identified by *name* within *category_id*, or ``None``."""
        stmt = self._base_select().where(
            AssetClass.category_id == category_id, AssetClass.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_category(self, category_id: UUID) -> list[AssetClass]:
        """Every class nested under *category_id*."""
        stmt = self._base_select().where(AssetClass.category_id == category_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetClassRepository"]
