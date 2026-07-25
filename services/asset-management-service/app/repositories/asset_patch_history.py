"""Repository for :class:`app.models.asset_patch_history.AssetPatchHistoryEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_patch_history import AssetPatchHistoryEntry


class AssetPatchHistoryRepository(BaseRepository[AssetPatchHistoryEntry]):
    """CRUD plus lookup for :class:`AssetPatchHistoryEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetPatchHistoryEntry, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetPatchHistoryEntry]:
        """Every patch/security update applied to *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetPatchHistoryEntry.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetPatchHistoryEntry.applied_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetPatchHistoryRepository"]
