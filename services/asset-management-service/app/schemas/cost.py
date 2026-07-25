"""Response schemas for ``GET /assets/{id}/costs``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CostType


class AssetCostResponse(BaseModel):
    """One cost entry incurred against a managed asset."""

    id: UUID
    managed_asset_id: UUID
    cost_type: CostType
    amount: float
    currency: str
    incurred_at: datetime
    description: str | None


class AssetCostSummaryResponse(BaseModel):
    """A managed asset's full cost history plus computed Total Cost of
    Ownership ("Total Cost of Ownership (TCO)").
    """

    managed_asset_id: UUID
    total_cost_of_ownership: float
    by_cost_type: dict[str, float]
    entries: list[AssetCostResponse]


class AssetBudgetResponse(BaseModel):
    """One fiscal-year budget allocation for a managed asset."""

    id: UUID
    managed_asset_id: UUID
    fiscal_year: int
    allocated_amount: float
    spent_amount: float
    currency: str


__all__ = ["AssetBudgetResponse", "AssetCostResponse", "AssetCostSummaryResponse"]
