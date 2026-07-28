"""``GET /monitoring/sla``. Per docs/044 REST list. ``POST
/monitoring/sla`` has no REST list entry of its own -- added directly:
without a create endpoint there is no way to register a Service Level
Agreement at all, the same "required capability with no REST list
entry" precedent applied throughout this service's own API layer.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SLASvc
from app.models.monitoring_sla import MonitoringSLA
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.sla import MonitoringSLACreateRequest, MonitoringSLAResponse

router = APIRouter(prefix="/monitoring/sla", tags=["Monitoring SLA"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def sla_to_response(sla: MonitoringSLA) -> MonitoringSLAResponse:
    return MonitoringSLAResponse(
        id=sla.id,
        organization_id=sla.organization_id,
        target_id=sla.target_id,
        sla_type=sla.sla_type,
        objective_percentage=sla.objective_percentage,
        actual_percentage=sla.actual_percentage,
        status=sla.status,
        period_start=sla.period_start,
        period_end=sla.period_end,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringSLAResponse]])
async def list_sla(
    organization_id: UUID, slas: SLASvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringSLAResponse]]:
    """List every SLA belonging to *organization_id*."""
    records = await slas.list_for_org(organization_id)
    data = [sla_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring SLAs retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringSLAResponse], status_code=201)
async def create_sla(
    body: MonitoringSLACreateRequest, slas: SLASvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringSLAResponse]:
    """Register a new SLA objective."""
    sla = await slas.create(
        organization_id=body.organization_id,
        target_id=body.target_id,
        sla_type=body.sla_type,
        objective_percentage=body.objective_percentage,
        period_start=body.period_start,
        period_end=body.period_end,
    )
    return SuccessResponse(
        message="Monitoring SLA created.", data=sla_to_response(sla), meta=_meta()
    )


__all__ = ["router", "sla_to_response"]
