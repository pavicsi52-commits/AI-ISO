"""Repository for :class:`app.models.asset_firmware.AssetFirmware`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_firmware import AssetFirmware


class AssetFirmwareRepository(BaseRepository[AssetFirmware]):
    """CRUD plus lookup for :class:`AssetFirmware`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetFirmware, tenant_scope=tenant_scope)

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetFirmware | None:
        """Return *managed_asset_id*'s current firmware state, or ``None``."""
        stmt = self._base_select().where(AssetFirmware.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetFirmwareRepository"]
