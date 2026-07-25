"""Repository for :class:`app.models.asset_change_history.AssetChangeHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_change_history import AssetChangeHistoryEntry


class AssetChangeHistoryRepository(BaseRepository[AssetChangeHistoryEntry]):
    """CRUD plus lookup for :class:`AssetChangeHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetChangeHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetChangeHistoryEntry]:
        """Every narrative timeline entry for *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetChangeHistoryEntry.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetChangeHistoryEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetChangeHistoryRepository"]
