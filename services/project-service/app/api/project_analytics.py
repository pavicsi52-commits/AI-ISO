"""``GET /projects/{id}/analytics``. Per docs/034 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import ProjSvc, StatisticsSvc, require_project_member
from app.models.project_statistics import ProjectStatistics
from app.schemas.project_statistics import ProjectStatisticsResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/projects/{project_id}/analytics", tags=["Project Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(statistics: ProjectStatistics) -> ProjectStatisticsResponse:
    return ProjectStatisticsResponse(
        project_id=statistics.project_id,
        member_count=statistics.member_count,
        automation_count=statistics.automation_count,
        workflow_count=statistics.workflow_count,
        validation_count=statistics.validation_count,
        inventory_count=statistics.inventory_count,
        connector_count=statistics.connector_count,
        ai_usage_count=statistics.ai_usage_count,
        storage_usage_bytes=statistics.storage_usage_bytes,
        execution_count=statistics.execution_count,
        failure_count=statistics.failure_count,
        success_count=statistics.success_count,
        success_rate_percent=float(statistics.success_rate_percent),
        computed_at=statistics.computed_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[ProjectStatisticsResponse],
    dependencies=[Depends(require_project_member)],
)
async def get_analytics(
    project_id: UUID, projects: ProjSvc, statistics: StatisticsSvc
) -> SuccessResponse[ProjectStatisticsResponse]:
    """Return a project's usage analytics ("Collect ...")."""
    project = await projects.get_by_id(project_id)
    record = await statistics.get_or_recompute(project_id, organization_id=project.organization_id)
    return SuccessResponse(message="Analytics retrieved.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
