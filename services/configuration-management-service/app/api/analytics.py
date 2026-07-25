"""``GET /configurations/analytics``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, StatisticsSvc
from app.models.configuration_statistics import ConfigurationStatistics
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import ConfigurationStatisticsResponse

router = APIRouter(prefix="/configurations", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def statistics_to_response(
    snapshot: ConfigurationStatistics,
) -> ConfigurationStatisticsResponse:
    return ConfigurationStatisticsResponse(
        total_profiles=snapshot.total_profiles,
        total_versions=snapshot.total_versions,
        drift_statistics=snapshot.drift_statistics,
        compliance_scores=snapshot.compliance_scores,
        rollback_statistics=snapshot.rollback_statistics,
        deployment_readiness=snapshot.deployment_readiness,
        environment_distribution=snapshot.environment_distribution,
        change_frequency=snapshot.change_frequency,
        computed_at=snapshot.computed_at,
    )


@router.get("/analytics", response_model=SuccessResponse[ConfigurationStatisticsResponse])
async def get_analytics(
    organization_id: UUID, statistics: StatisticsSvc, _caller: CurrentUserId
) -> SuccessResponse[ConfigurationStatisticsResponse]:
    """Return *organization_id*'s configuration-management analytics rollup ("Collect")."""
    snapshot = await statistics.get_for_org(organization_id)
    return SuccessResponse(
        message="Configuration analytics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


__all__ = ["router", "statistics_to_response"]
