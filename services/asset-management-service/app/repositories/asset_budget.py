"""Repository for :class:`app.models.asset_budget.AssetBudget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_budget import AssetBudget


class AssetBudgetRepository(BaseRepository[AssetBudget]):
    """CRUD plus lookup for :class:`AssetBudget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetBudget, tenant_scope=tenant_scope)

    async def get_for_managed_asset_and_year(
        self, managed_asset_id: UUID, fiscal_year: int
    ) -> AssetBudget | None:
        """Return *managed_asset_id*'s budget allocation for *fiscal_year*, or ``None``."""
        stmt = self._base_select().where(
            AssetBudget.managed_asset_id == managed_asset_id,
            AssetBudget.fiscal_year == fiscal_year,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetBudget]:
        """Every fiscal-year budget allocation for *managed_asset_id*."""
        stmt = self._base_select().where(AssetBudget.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetBudgetRepository"]
