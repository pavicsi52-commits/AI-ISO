"""``/oncall-schedules`` -- rotations, overrides, and who is on call now."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, OnCallSvc
from app.models.alert_oncall_schedule import AlertOnCallSchedule
from app.schemas.oncall_schedule import (
    OnCallCurrentResponse,
    OnCallScheduleCreateRequest,
    OnCallScheduleResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/oncall-schedules", tags=["On-Call Schedules"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def schedule_to_response(schedule: AlertOnCallSchedule) -> OnCallScheduleResponse:
    """Map an :class:`AlertOnCallSchedule` row onto its own response schema."""
    return OnCallScheduleResponse(
        id=schedule.id,
        organization_id=schedule.organization_id,
        project_id=schedule.project_id,
        name=schedule.name,
        rotation_type=schedule.rotation_type,
        timezone=schedule.timezone,
        participants=schedule.participants,
        overrides=schedule.overrides,
        holiday_calendar=schedule.holiday_calendar,
        enabled=schedule.enabled,
    )


@router.get("", response_model=SuccessResponse[list[OnCallScheduleResponse]])
async def list_oncall_schedules(
    organization_id: UUID, schedules: OnCallSvc, _caller: CurrentUserId
) -> SuccessResponse[list[OnCallScheduleResponse]]:
    """List every on-call schedule for an organization."""
    records = await schedules.list_for_org(organization_id)
    data = [schedule_to_response(record) for record in records]
    return SuccessResponse(message="On-call schedules retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[OnCallScheduleResponse], status_code=201)
async def create_oncall_schedule(
    body: OnCallScheduleCreateRequest, schedules: OnCallSvc, _caller: CurrentUserId
) -> SuccessResponse[OnCallScheduleResponse]:
    """Create an on-call schedule."""
    schedule = await schedules.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        rotation_type=body.rotation_type,
        timezone=body.timezone,
        participants=body.participants,
        overrides=body.overrides,
        holiday_calendar=body.holiday_calendar,
        enabled=body.enabled,
    )
    return SuccessResponse(
        message="On-call schedule created.", data=schedule_to_response(schedule), meta=_meta()
    )


@router.get("/{schedule_id}/current", response_model=SuccessResponse[OnCallCurrentResponse])
async def get_current_oncall(
    schedule_id: UUID, schedules: OnCallSvc, _caller: CurrentUserId
) -> SuccessResponse[OnCallCurrentResponse]:
    """Who is on call for a schedule right now.

    ``user_id`` is ``null`` when nobody is -- a holiday, a disabled
    schedule, or one with no participants. Added beyond docs/045's own
    literal REST list: without it, every rotation/override/holiday rule
    this service computes would be unreachable by any caller.

    Raises:
        NotFoundError: If no such schedule exists.
    """
    user_id = await schedules.current_oncall(schedule_id)
    return SuccessResponse(
        message="Current on-call retrieved.",
        data=OnCallCurrentResponse(schedule_id=schedule_id, user_id=user_id),
        meta=_meta(),
    )


__all__ = ["router", "schedule_to_response"]
