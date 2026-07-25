"""``GET /inventory/statistics``. Per docs/036 REST list and
"ANALYTICS": Asset Count, Asset Types, Health Distribution, Lifecycle
Distribution, OS Distribution, Vendor Distribution, Location
Distribution, Relationship Count.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import InventoryStatisticsResponse

router = APIRouter(prefix="/inventory/statistics", tags=["Statistics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[InventoryStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[InventoryStatisticsResponse]:
    """Return *organization_id*'s current-state inventory rollup."""
    snapshot = await statistics.get_for_org(organization_id)
    data = InventoryStatisticsResponse(
        total_assets=snapshot.total_assets,
        total_relationships=snapshot.total_relationships,
        type_distribution=snapshot.type_distribution,
        health_distribution=snapshot.health_distribution,
        lifecycle_distribution=snapshot.lifecycle_distribution,
        os_distribution=snapshot.os_distribution,
        vendor_distribution=snapshot.vendor_distribution,
        location_distribution=snapshot.location_distribution,
        computed_at=snapshot.computed_at,
    )
    return SuccessResponse(message="Statistics retrieved.", data=data, meta=_meta())


__all__ = ["router"]
