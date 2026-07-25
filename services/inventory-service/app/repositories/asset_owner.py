"""Repository for :class:`app.models.asset_owner.AssetOwner`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_owner import AssetOwner
from app.models.enums import OwnerType


class AssetOwnerRepository(BaseRepository[AssetOwner]):
    """CRUD plus lookup for :class:`AssetOwner`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetOwner, tenant_scope=tenant_scope)

    async def get_for_role(self, asset_id: UUID, owner_type: OwnerType) -> AssetOwner | None:
        """Return *asset_id*'s owner for *owner_type*, or ``None``."""
        stmt = self._base_select().where(
            AssetOwner.asset_id == asset_id, AssetOwner.owner_type == owner_type
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetOwner]:
        """Every ownership-role assignment on *asset_id*."""
        stmt = self._base_select().where(AssetOwner.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetOwnerRepository"]
