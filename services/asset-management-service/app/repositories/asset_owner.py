"""Repository for :class:`app.models.asset_owner.AssetOwner`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_owner import AssetOwner
from app.models.enums import OwnerRole


class AssetOwnerRepository(BaseRepository[AssetOwner]):
    """CRUD plus lookup for :class:`AssetOwner`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetOwner, tenant_scope=tenant_scope)

    async def get_for_role(self, managed_asset_id: UUID, role: OwnerRole) -> AssetOwner | None:
        """Return *managed_asset_id*'s owner for *role*, or ``None``."""
        stmt = self._base_select().where(
            AssetOwner.managed_asset_id == managed_asset_id, AssetOwner.role == role
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetOwner]:
        """Every ownership-role assignment on *managed_asset_id*."""
        stmt = self._base_select().where(AssetOwner.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetOwnerRepository"]
