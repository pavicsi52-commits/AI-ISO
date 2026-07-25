"""Repository for :class:`app.models.asset_history.AssetHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_history import AssetHistoryEntry


class AssetHistoryRepository(BaseRepository[AssetHistoryEntry]):
    """CRUD plus lookup for :class:`AssetHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetHistoryEntry]:
        """Every narrative timeline entry for *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetHistoryEntry.asset_id == asset_id)
            .order_by(desc(AssetHistoryEntry.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetHistoryRepository"]
