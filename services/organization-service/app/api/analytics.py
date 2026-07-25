"""``GET /organizations/{id}/analytics``. Per docs/033 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc, require_member
from app.models.statistics import OrganizationStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import OrganizationStatisticsResponse

router = APIRouter(
    prefix="/organizations/{organization_id}/analytics", tags=["Organization Analytics"]
)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(statistics: OrganizationStatistics) -> OrganizationStatisticsResponse:
    return OrganizationStatisticsResponse(
        organization_id=statistics.organization_id,
        user_count=statistics.user_count,
        project_count=statistics.project_count,
        asset_count=statistics.asset_count,
        workflow_count=statistics.workflow_count,
        automation_count=statistics.automation_count,
        validation_count=statistics.validation_count,
        storage_usage_bytes=statistics.storage_usage_bytes,
        api_usage_count=statistics.api_usage_count,
        ai_usage_count=statistics.ai_usage_count,
        license_utilization_percent=float(statistics.license_utilization_percent),
        computed_at=statistics.computed_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[OrganizationStatisticsResponse],
    dependencies=[Depends(require_member)],
)
async def get_analytics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationStatisticsResponse]:
    """Return an organization's usage analytics ("Collect ...")."""
    record = await statistics.get_or_recompute(organization_id)
    return SuccessResponse(message="Analytics retrieved.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
