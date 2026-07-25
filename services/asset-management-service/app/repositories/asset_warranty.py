"""Repository for :class:`app.models.asset_warranty.AssetWarranty`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_warranty import AssetWarranty


class AssetWarrantyRepository(BaseRepository[AssetWarranty]):
    """CRUD plus lookup for :class:`AssetWarranty`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetWarranty, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetWarranty]:
        """Every warranty period recorded for *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetWarranty.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetWarranty.end_date))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current_for_managed_asset(self, managed_asset_id: UUID) -> AssetWarranty | None:
        """Return *managed_asset_id*'s warranty period with the latest end date, or ``None``."""
        stmt = (
            self._base_select()
            .where(AssetWarranty.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetWarranty.end_date))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_expiring_before(self, cutoff: datetime) -> list[AssetWarranty]:
        """Every warranty period ending on or before *cutoff*, for expiration alerts."""
        stmt = self._base_select().where(
            AssetWarranty.end_date <= cutoff, AssetWarranty.expiration_alert_sent.is_(False)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetWarrantyRepository"]
