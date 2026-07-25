"""``GET /assets/analytics``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import AssetStatisticsResponse

router = APIRouter(prefix="/assets", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("/analytics", response_model=SuccessResponse[AssetStatisticsResponse])
async def get_analytics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetStatisticsResponse]:
    """Return an organization's asset-management analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    data = AssetStatisticsResponse(
        total_managed_assets=snapshot.total_managed_assets,
        asset_growth=snapshot.asset_growth,
        status_distribution=snapshot.status_distribution,
        criticality_distribution=snapshot.criticality_distribution,
        lifecycle_distribution=snapshot.lifecycle_distribution,
        compliance_distribution=snapshot.compliance_distribution,
        risk_distribution=snapshot.risk_distribution,
        cost_trends=snapshot.cost_trends,
        maintenance_trends=snapshot.maintenance_trends,
        vendor_performance=snapshot.vendor_performance,
        computed_at=snapshot.computed_at,
    )
    return SuccessResponse(message="Analytics retrieved.", data=data, meta=_meta())


__all__ = ["router"]
