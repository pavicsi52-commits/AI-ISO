"""``GET /playbooks/statistics``. Per docs/041 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.playbook_statistics import PlaybookStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import PlaybookStatisticsResponse

router = APIRouter(prefix="/playbooks/statistics", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(snapshot: PlaybookStatistics) -> PlaybookStatisticsResponse:
    return PlaybookStatisticsResponse(
        total_playbooks=snapshot.total_playbooks,
        total_versions=snapshot.total_versions,
        total_downloads=snapshot.total_downloads,
        approvals_summary=snapshot.approvals_summary,
        validation_results_summary=snapshot.validation_results_summary,
        version_growth=snapshot.version_growth,
        most_used_content=snapshot.most_used_content,
        deprecated_content_count=snapshot.deprecated_content_count,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[PlaybookStatisticsResponse])
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[PlaybookStatisticsResponse]:
    """Return *organization_id*'s playbook-repository analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Playbook statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
