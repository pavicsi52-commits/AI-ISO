"""Repository for :class:`app.models.asset_cost.AssetCost`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_cost import AssetCost
from app.models.enums import CostType


class AssetCostRepository(BaseRepository[AssetCost]):
    """CRUD plus lookup for :class:`AssetCost`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetCost, tenant_scope=tenant_scope)

    async def list_for_managed_asset(
        self, managed_asset_id: UUID, *, cost_type: CostType | None = None
    ) -> list[AssetCost]:
        """Every cost entry for *managed_asset_id*, newest first, optionally
        narrowed to a single *cost_type*.
        """
        stmt = self._base_select().where(AssetCost.managed_asset_id == managed_asset_id)
        if cost_type is not None:
            stmt = stmt.where(AssetCost.cost_type == cost_type)
        stmt = stmt.order_by(desc(AssetCost.incurred_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetCostRepository"]
