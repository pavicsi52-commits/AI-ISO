"""``GET /monitoring/health``. Per docs/044 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, HealthSvc
from app.models.monitoring_health import MonitoringHealth
from app.schemas.health_check import MonitoringHealthResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/health", tags=["Monitoring Health"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def health_to_response(record: MonitoringHealth) -> MonitoringHealthResponse:
    return MonitoringHealthResponse(
        id=record.id,
        organization_id=record.organization_id,
        target_id=record.target_id,
        check_type=record.check_type,
        status=record.status,
        message=record.message,
        checked_at=record.checked_at,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringHealthResponse]])
async def list_health(
    target_id: UUID, health: HealthSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringHealthResponse]]:
    """List every health-check result recorded for *target_id*, most recent first."""
    records = await health.list_for_target(target_id)
    data = [health_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring health results retrieved.", data=data, meta=_meta())


__all__ = ["health_to_response", "router"]
