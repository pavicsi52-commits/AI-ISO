"""Cost tracking and budgeting. Per docs/038 "COST MANAGEMENT" "Track":
Acquisition, Operational, Maintenance, Support, Energy, Cloud,
Subscription, Repair, Replacement Cost, Total Cost of Ownership (TCO).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from app.models.asset_budget import AssetBudget
from app.models.asset_cost import AssetCost
from app.models.enums import CostType
from app.repositories.asset_budget import AssetBudgetRepository
from app.repositories.asset_cost import AssetCostRepository


class CostService:
    """Records costs and budgets, and computes Total Cost of Ownership."""

    def __init__(self, costs: AssetCostRepository, budgets: AssetBudgetRepository) -> None:
        self._costs = costs
        self._budgets = budgets

    async def list_for_managed_asset(
        self, managed_asset_id: UUID, *, cost_type: CostType | None = None
    ) -> list[AssetCost]:
        """Every cost entry for *managed_asset_id*, newest first."""
        return await self._costs.list_for_managed_asset(managed_asset_id, cost_type=cost_type)

    async def record_cost(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        cost_type: CostType,
        amount: float,
        currency: str,
        incurred_at: datetime,
        description: str | None,
    ) -> AssetCost:
        """Record one cost entry against *managed_asset_id* ("Track")."""
        return await self._costs.create(
            AssetCost(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                cost_type=cost_type,
                amount=amount,
                currency=currency,
                incurred_at=incurred_at,
                description=description,
            )
        )

    async def get_total_cost_of_ownership(
        self, managed_asset_id: UUID
    ) -> tuple[float, dict[str, float], list[AssetCost]]:
        """*managed_asset_id*'s Total Cost of Ownership, broken down by
        cost type, alongside its full cost history ("Total Cost of
        Ownership (TCO)").
        """
        entries = await self.list_for_managed_asset(managed_asset_id)
        by_type: dict[str, float] = defaultdict(float)
        total = 0.0
        for entry in entries:
            by_type[str(entry.cost_type)] += float(entry.amount)
            total += float(entry.amount)
        return total, dict(by_type), entries

    async def list_budgets(self, managed_asset_id: UUID) -> list[AssetBudget]:
        """Every fiscal-year budget allocation for *managed_asset_id*."""
        return await self._budgets.list_for_managed_asset(managed_asset_id)

    async def upsert_budget(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        fiscal_year: int,
        allocated_amount: float,
        spent_amount: float,
        currency: str,
    ) -> AssetBudget:
        """Create or replace *managed_asset_id*'s budget allocation for
        *fiscal_year*.
        """
        existing = await self._budgets.get_for_managed_asset_and_year(managed_asset_id, fiscal_year)
        if existing is not None:
            existing.allocated_amount = allocated_amount
            existing.spent_amount = spent_amount
            existing.currency = currency
            return existing
        return await self._budgets.create(
            AssetBudget(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                fiscal_year=fiscal_year,
                allocated_amount=allocated_amount,
                spent_amount=spent_amount,
                currency=currency,
            )
        )


__all__ = ["CostService"]
