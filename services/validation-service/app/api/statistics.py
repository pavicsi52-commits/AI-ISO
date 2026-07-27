"""``GET /validation/statistics``. Per docs/043 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.validation_statistics import ValidationStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import ValidationStatisticsResponse

router = APIRouter(prefix="/validation/statistics", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(snapshot: ValidationStatistics) -> ValidationStatisticsResponse:
    return ValidationStatisticsResponse(
        total_profiles=snapshot.total_profiles,
        total_executions=snapshot.total_executions,
        pass_rate=snapshot.pass_rate,
        failure_rate=snapshot.failure_rate,
        average_duration_seconds=snapshot.average_duration_seconds,
        top_failures=snapshot.top_failures,
        trend_data=snapshot.trend_data,
        asset_health_trends=snapshot.asset_health_trends,
        compliance_trends=snapshot.compliance_trends,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[ValidationStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationStatisticsResponse]:
    """Return *organization_id*'s validation analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Validation statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
