"""Aggregated backend health (docs/056 "REST APIs": ``GET /gateway/health``)."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import HealthMonitorSvc
from app.models.enums import HealthState
from app.schemas.gateway import ServiceHealthResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/health", tags=["Gateway Health"])

_SEVERITY: Final[dict[HealthState, int]] = {
    HealthState.HEALTHY: 0,
    HealthState.MAINTENANCE: 1,
    HealthState.WARNING: 2,
    HealthState.DEGRADED: 3,
    HealthState.UNHEALTHY: 4,
    HealthState.UNKNOWN: 5,
}
"""Worst-first ranking for rolling many instances up into one overall status.
``UNKNOWN`` ranks worse than ``UNHEALTHY`` -- no visibility into an instance
is treated as more concerning than a confirmed failure, not less."""


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[dict[str, object]],
    summary="Aggregated backend health across every registered service",
)
async def gateway_health(
    organization_id: UUID, health: HealthMonitorSvc
) -> SuccessResponse[dict[str, object]]:
    """The last-probed health of every backend instance in this organization.

    Health probing itself happens on a periodic worker sweep, not on this
    request -- this endpoint reports the most recently persisted result,
    the same "cross-replica visibility" snapshot every instance's own
    circuit breaker reacts to.
    """
    rows = await health.list_for_org(organization_id)
    instances = [ServiceHealthResponse.model_validate(row) for row in rows]
    overall = (
        max((HealthState(one.status) for one in instances), key=lambda s: _SEVERITY[s])
        if instances
        else HealthState.UNKNOWN
    )
    return SuccessResponse(
        message="Gateway health computed.",
        data={"overall_status": overall.value, "instances": instances},
        meta=_meta(),
    )


__all__ = ["router"]
