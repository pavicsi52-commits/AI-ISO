"""``GET /assets/{id}/health``. Per docs/038 REST list. Named
``asset_health`` (not ``health``) to avoid colliding with
``app/api/health.py``'s own service health/readiness/liveness probes.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, HealthSvc
from app.models.asset_health_rollup import AssetHealthRollup
from app.schemas.asset_health import AssetHealthRollupResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Health Rollups"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def health_rollup_to_response(rollup: AssetHealthRollup) -> AssetHealthRollupResponse:
    return AssetHealthRollupResponse(
        id=rollup.id,
        managed_asset_id=rollup.managed_asset_id,
        monitoring_status=rollup.monitoring_status,
        validation_status=rollup.validation_status,
        discovery_status=rollup.discovery_status,
        automation_status=rollup.automation_status,
        incident_count=rollup.incident_count,
        performance_indicators=rollup.performance_indicators,
        availability_percent=(
            float(rollup.availability_percent) if rollup.availability_percent is not None else None
        ),
        health_score=float(rollup.health_score),
        health_trend=rollup.health_trend,
        computed_at=rollup.computed_at,
    )


@router.get("/{managed_asset_id}/health", response_model=SuccessResponse[AssetHealthRollupResponse])
async def get_health_rollup(
    managed_asset_id: UUID, health: HealthSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetHealthRollupResponse]:
    """Return a managed asset's cached operational-health rollup ("Aggregate").

    Raises:
        NotFoundError: If no health rollup has been computed yet.
    """
    rollup = await health.get_for_managed_asset(managed_asset_id)
    if rollup is None:
        raise NotFoundError(f"Managed asset '{managed_asset_id}' has no health rollup yet.")
    return SuccessResponse(
        message="Health rollup retrieved.", data=health_rollup_to_response(rollup), meta=_meta()
    )


__all__ = ["health_rollup_to_response", "router"]
