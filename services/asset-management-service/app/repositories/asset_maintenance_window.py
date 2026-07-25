"""Repository for :class:`app.models.asset_maintenance_window.AssetMaintenanceWindow`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_maintenance_window import AssetMaintenanceWindow


class AssetMaintenanceWindowRepository(BaseRepository[AssetMaintenanceWindow]):
    """CRUD plus lookup for :class:`AssetMaintenanceWindow`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetMaintenanceWindow, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetMaintenanceWindow]:
        """Every maintenance window for *managed_asset_id*, soonest first."""
        stmt = (
            self._base_select()
            .where(AssetMaintenanceWindow.managed_asset_id == managed_asset_id)
            .order_by(asc(AssetMaintenanceWindow.starts_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_starting_before(self, cutoff: datetime) -> list[AssetMaintenanceWindow]:
        """Every approved window starting on or before *cutoff*, for notifications."""
        stmt = self._base_select().where(
            AssetMaintenanceWindow.starts_at <= cutoff,
            AssetMaintenanceWindow.approved.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetMaintenanceWindowRepository"]
