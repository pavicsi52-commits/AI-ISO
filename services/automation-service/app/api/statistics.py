"""``GET /automation/statistics``. Per docs/040 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.automation_statistics import AutomationStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import AutomationStatisticsResponse

router = APIRouter(prefix="/automation/statistics", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(snapshot: AutomationStatistics) -> AutomationStatisticsResponse:
    return AutomationStatisticsResponse(
        total_jobs=snapshot.total_jobs,
        total_executions=snapshot.total_executions,
        success_rate=snapshot.success_rate,
        failure_rate=snapshot.failure_rate,
        average_runtime_seconds=snapshot.average_runtime_seconds,
        resource_usage=snapshot.resource_usage,
        connector_usage=snapshot.connector_usage,
        top_failed_jobs=snapshot.top_failed_jobs,
        most_executed_jobs=snapshot.most_executed_jobs,
        execution_heatmap=snapshot.execution_heatmap,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[AutomationStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationStatisticsResponse]:
    """Return *organization_id*'s automation analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Automation statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
