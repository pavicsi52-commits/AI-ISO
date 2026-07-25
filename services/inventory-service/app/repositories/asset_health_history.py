"""Repository for :class:`app.models.asset_health_history.AssetHealthHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_health_history import AssetHealthHistoryEntry


class AssetHealthHistoryRepository(BaseRepository[AssetHealthHistoryEntry]):
    """CRUD plus lookup for :class:`AssetHealthHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetHealthHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetHealthHistoryEntry]:
        """Every health check result for *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetHealthHistoryEntry.asset_id == asset_id)
            .order_by(desc(AssetHealthHistoryEntry.checked_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetHealthHistoryRepository"]
