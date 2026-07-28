"""``GET /monitoring/slo``. Per docs/044 REST list. ``POST
/monitoring/slo`` has no REST list entry of its own -- added directly,
matching :mod:`app.api.monitoring_sla`'s own identical reasoning.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SLOSvc
from app.models.monitoring_slo import MonitoringSLO
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.slo import MonitoringSLOCreateRequest, MonitoringSLOResponse

router = APIRouter(prefix="/monitoring/slo", tags=["Monitoring SLO"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def slo_to_response(slo: MonitoringSLO) -> MonitoringSLOResponse:
    return MonitoringSLOResponse(
        id=slo.id,
        organization_id=slo.organization_id,
        target_id=slo.target_id,
        slo_type=slo.slo_type,
        objective_value=slo.objective_value,
        actual_value=slo.actual_value,
        error_budget_remaining_percentage=slo.error_budget_remaining_percentage,
        status=slo.status,
        period_start=slo.period_start,
        period_end=slo.period_end,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringSLOResponse]])
async def list_slo(
    organization_id: UUID, slos: SLOSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringSLOResponse]]:
    """List every SLO belonging to *organization_id*."""
    records = await slos.list_for_org(organization_id)
    data = [slo_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring SLOs retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringSLOResponse], status_code=201)
async def create_slo(
    body: MonitoringSLOCreateRequest, slos: SLOSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringSLOResponse]:
    """Register a new SLO target."""
    slo = await slos.create(
        organization_id=body.organization_id,
        target_id=body.target_id,
        slo_type=body.slo_type,
        objective_value=body.objective_value,
        period_start=body.period_start,
        period_end=body.period_end,
    )
    return SuccessResponse(
        message="Monitoring SLO created.", data=slo_to_response(slo), meta=_meta()
    )


__all__ = ["router", "slo_to_response"]
