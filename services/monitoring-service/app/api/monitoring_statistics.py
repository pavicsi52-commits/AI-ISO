"""``GET /monitoring/statistics``. Per docs/044 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.monitoring_statistics import MonitoringStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import MonitoringStatisticsResponse

router = APIRouter(prefix="/monitoring/statistics", tags=["Monitoring Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(snapshot: MonitoringStatistics) -> MonitoringStatisticsResponse:
    return MonitoringStatisticsResponse(
        total_targets=snapshot.total_targets,
        total_metrics_collected=snapshot.total_metrics_collected,
        average_availability_percentage=snapshot.average_availability_percentage,
        average_health_score=snapshot.average_health_score,
        sla_compliance_percentage=snapshot.sla_compliance_percentage,
        slo_compliance_percentage=snapshot.slo_compliance_percentage,
        top_threshold_breaches=snapshot.top_threshold_breaches,
        trend_data=snapshot.trend_data,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[MonitoringStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringStatisticsResponse]:
    """Return *organization_id*'s monitoring analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Monitoring statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
