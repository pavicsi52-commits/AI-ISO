"""``GET /assets/{id}/risk``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RiskSvc
from app.models.asset_risk import AssetRisk
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.risk import AssetRiskResponse

router = APIRouter(prefix="/assets", tags=["Risk"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def risk_to_response(evaluation: AssetRisk) -> AssetRiskResponse:
    return AssetRiskResponse(
        id=evaluation.id,
        managed_asset_id=evaluation.managed_asset_id,
        risk_type=evaluation.risk_type,
        level=evaluation.level,
        score=float(evaluation.score),
        mitigation_plan=evaluation.mitigation_plan,
        evaluated_at=evaluation.evaluated_at,
    )


@router.get("/{managed_asset_id}/risk", response_model=SuccessResponse[list[AssetRiskResponse]])
async def list_risk(
    managed_asset_id: UUID, risk: RiskSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetRiskResponse]]:
    """List every risk-type evaluation for a managed asset ("Risk History")."""
    records = await risk.list_for_managed_asset(managed_asset_id)
    data = [risk_to_response(record) for record in records]
    return SuccessResponse(message="Risk evaluations retrieved.", data=data, meta=_meta())


__all__ = ["risk_to_response", "router"]
