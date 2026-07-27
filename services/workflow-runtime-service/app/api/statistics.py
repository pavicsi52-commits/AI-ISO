"""``GET /workflow/statistics``. Per docs/042 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.workflow_statistics import WorkflowStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import WorkflowStatisticsResponse

router = APIRouter(prefix="/workflow/statistics", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(snapshot: WorkflowStatistics) -> WorkflowStatisticsResponse:
    return WorkflowStatisticsResponse(
        total_workflows=snapshot.total_workflows,
        total_executions=snapshot.total_executions,
        success_rate=snapshot.success_rate,
        failure_rate=snapshot.failure_rate,
        average_duration_seconds=snapshot.average_duration_seconds,
        checkpoint_count=snapshot.checkpoint_count,
        approval_count=snapshot.approval_count,
        replay_count=snapshot.replay_count,
        rollback_count=snapshot.rollback_count,
        node_statistics=snapshot.node_statistics,
        execution_trends=snapshot.execution_trends,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[WorkflowStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowStatisticsResponse]:
    """Return *organization_id*'s workflow-runtime analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Workflow statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
