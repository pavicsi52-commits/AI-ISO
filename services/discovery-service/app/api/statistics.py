"""``GET /discovery/statistics``. Per docs/037 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.discovery_statistics import DiscoveryStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import DiscoveryStatisticsResponse

router = APIRouter(prefix="/discovery/statistics", tags=["Statistics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(statistics: DiscoveryStatistics) -> DiscoveryStatisticsResponse:
    return DiscoveryStatisticsResponse(
        total_jobs=statistics.total_jobs,
        total_assets_discovered=statistics.total_assets_discovered,
        total_relationships_discovered=statistics.total_relationships_discovered,
        jobs_by_mode=statistics.jobs_by_mode,
        assets_by_classification=statistics.assets_by_classification,
        failures_by_reason=statistics.failures_by_reason,
        last_discovery_at=statistics.last_discovery_at,
        computed_at=statistics.computed_at,
    )


@router.get("", response_model=SuccessResponse[DiscoveryStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[DiscoveryStatisticsResponse]:
    """Return *organization_id*'s cached discovery analytics snapshot,
    recomputing it if none exists yet.
    """
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Discovery statistics retrieved.", data=_to_response(snapshot), meta=_meta()
    )


__all__ = ["router"]
