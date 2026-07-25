"""``GET /assets/{id}/costs``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CostSvc, CurrentUserId
from app.models.asset_cost import AssetCost
from app.schemas.cost import AssetCostResponse, AssetCostSummaryResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Costs"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def cost_to_response(cost: AssetCost) -> AssetCostResponse:
    return AssetCostResponse(
        id=cost.id,
        managed_asset_id=cost.managed_asset_id,
        cost_type=cost.cost_type,
        amount=float(cost.amount),
        currency=cost.currency,
        incurred_at=cost.incurred_at,
        description=cost.description,
    )


@router.get("/{managed_asset_id}/costs", response_model=SuccessResponse[AssetCostSummaryResponse])
async def get_costs(
    managed_asset_id: UUID, costs: CostSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetCostSummaryResponse]:
    """Return a managed asset's full cost history and computed Total Cost
    of Ownership ("Total Cost of Ownership (TCO)").
    """
    total, by_type, entries = await costs.get_total_cost_of_ownership(managed_asset_id)
    data = AssetCostSummaryResponse(
        managed_asset_id=managed_asset_id,
        total_cost_of_ownership=total,
        by_cost_type=by_type,
        entries=[cost_to_response(entry) for entry in entries],
    )
    return SuccessResponse(message="Costs retrieved.", data=data, meta=_meta())


__all__ = ["cost_to_response", "router"]
