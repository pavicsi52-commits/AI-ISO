"""Repository for :class:`app.models.asset_maintenance.AssetMaintenance`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_maintenance import AssetMaintenance
from app.models.enums import MaintenanceStatus


class AssetMaintenanceRepository(BaseRepository[AssetMaintenance]):
    """CRUD plus lookup for :class:`AssetMaintenance`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetMaintenance, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetMaintenance]:
        """Every maintenance activity for *managed_asset_id*, soonest-scheduled first."""
        stmt = (
            self._base_select()
            .where(AssetMaintenance.managed_asset_id == managed_asset_id)
            .order_by(asc(AssetMaintenance.scheduled_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_before(self, cutoff: datetime) -> list[AssetMaintenance]:
        """Every scheduled, not-yet-completed maintenance activity due on or
        before *cutoff*, for the "Maintenance Calendar"/due-alert flow.
        """
        stmt = self._base_select().where(
            AssetMaintenance.scheduled_at <= cutoff,
            AssetMaintenance.status == MaintenanceStatus.SCHEDULED,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetMaintenanceRepository"]
