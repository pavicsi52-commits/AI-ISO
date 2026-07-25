"""Repository for :class:`app.models.asset_lifecycle_history.AssetLifecycleHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_lifecycle_history import AssetLifecycleHistoryEntry


class AssetLifecycleHistoryRepository(BaseRepository[AssetLifecycleHistoryEntry]):
    """CRUD plus lookup for :class:`AssetLifecycleHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetLifecycleHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetLifecycleHistoryEntry]:
        """Every lifecycle transition for *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetLifecycleHistoryEntry.asset_id == asset_id)
            .order_by(desc(AssetLifecycleHistoryEntry.transitioned_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetLifecycleHistoryRepository"]
