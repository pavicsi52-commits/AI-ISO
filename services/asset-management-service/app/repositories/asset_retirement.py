"""Repository for :class:`app.models.asset_retirement.AssetRetirement`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_retirement import AssetRetirement


class AssetRetirementRepository(BaseRepository[AssetRetirement]):
    """CRUD plus lookup for :class:`AssetRetirement`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetRetirement, tenant_scope=tenant_scope)

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetRetirement | None:
        """Return *managed_asset_id*'s retirement record, or ``None``."""
        stmt = self._base_select().where(AssetRetirement.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetRetirementRepository"]
