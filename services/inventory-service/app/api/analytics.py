"""``GET /inventory/analytics``. Per docs/036 REST list and
"ANALYTICS": Discovery Statistics, Growth Trends (extends
``GET /inventory/statistics`` with discovery-source breakdown and
30-day asset growth).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import InventoryAnalyticsResponse

router = APIRouter(prefix="/inventory/analytics", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[InventoryAnalyticsResponse])
async def get_analytics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[InventoryAnalyticsResponse]:
    """Return *organization_id*'s full analytics rollup, including
    discovery-source distribution and 30-day growth trend.
    """
    analytics = await statistics.get_analytics(organization_id)
    data = InventoryAnalyticsResponse.model_validate(analytics)
    return SuccessResponse(message="Analytics retrieved.", data=data, meta=_meta())


__all__ = ["router"]
