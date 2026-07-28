"""``GET /monitoring/targets``, ``POST /monitoring/targets``. Per docs/044 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TargetSvc
from app.models.monitoring_target import MonitoringTarget
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.target import MonitoringTargetCreateRequest, MonitoringTargetResponse

router = APIRouter(prefix="/monitoring/targets", tags=["Monitoring Targets"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def target_to_response(target: MonitoringTarget) -> MonitoringTargetResponse:
    return MonitoringTargetResponse(
        id=target.id,
        organization_id=target.organization_id,
        project_id=target.project_id,
        target_type=target.target_type,
        external_id=target.external_id,
        name=target.name,
        target_metadata=target.target_metadata,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringTargetResponse]])
async def list_targets(
    organization_id: UUID, targets: TargetSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringTargetResponse]]:
    """List every monitored target in *organization_id*."""
    records = await targets.list_for_org(organization_id)
    data = [target_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring targets retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringTargetResponse], status_code=201)
async def create_target(
    body: MonitoringTargetCreateRequest, targets: TargetSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringTargetResponse]:
    """Register a new monitoring target."""
    target = await targets.get_or_create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        target_type=body.target_type,
        external_id=body.external_id,
        name=body.name,
        target_metadata=body.target_metadata,
    )
    return SuccessResponse(
        message="Monitoring target registered.", data=target_to_response(target), meta=_meta()
    )


__all__ = ["router", "target_to_response"]
