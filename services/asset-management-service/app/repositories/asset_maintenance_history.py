"""Repository for :class:`app.models.asset_maintenance_history.AssetMaintenanceHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_maintenance_history import AssetMaintenanceHistoryEntry


class AssetMaintenanceHistoryRepository(BaseRepository[AssetMaintenanceHistoryEntry]):
    """CRUD plus lookup for :class:`AssetMaintenanceHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetMaintenanceHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_managed_asset(
        self, managed_asset_id: UUID
    ) -> list[AssetMaintenanceHistoryEntry]:
        """Every maintenance timeline entry for *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetMaintenanceHistoryEntry.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetMaintenanceHistoryEntry.occurred_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetMaintenanceHistoryRepository"]
