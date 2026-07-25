"""Repository for :class:`app.models.asset_status_history.AssetStatusHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_status_history import AssetStatusHistoryEntry


class AssetStatusHistoryRepository(BaseRepository[AssetStatusHistoryEntry]):
    """CRUD plus lookup for :class:`AssetStatusHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetStatusHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetStatusHistoryEntry]:
        """Every status transition for *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetStatusHistoryEntry.asset_id == asset_id)
            .order_by(desc(AssetStatusHistoryEntry.changed_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetStatusHistoryRepository"]
