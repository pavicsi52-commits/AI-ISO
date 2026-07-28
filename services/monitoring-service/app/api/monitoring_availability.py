"""``GET /monitoring/availability``. Per docs/044 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AvailabilitySvc, CurrentUserId
from app.models.monitoring_availability import MonitoringAvailability
from app.schemas.availability import MonitoringAvailabilityResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/availability", tags=["Monitoring Availability"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def availability_to_response(record: MonitoringAvailability) -> MonitoringAvailabilityResponse:
    return MonitoringAvailabilityResponse(
        id=record.id,
        organization_id=record.organization_id,
        target_id=record.target_id,
        status=record.status,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_seconds=record.duration_seconds,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringAvailabilityResponse]])
async def list_availability(
    target_id: UUID, availability: AvailabilitySvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringAvailabilityResponse]]:
    """List every availability interval recorded for *target_id*, oldest first."""
    records = await availability.list_for_target(target_id)
    data = [availability_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring availability retrieved.", data=data, meta=_meta())


__all__ = ["availability_to_response", "router"]
