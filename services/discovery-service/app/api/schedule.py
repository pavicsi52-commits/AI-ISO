"""``/discovery/schedules``. Per docs/037 REST list and "SCHEDULING":
"Integrate with Prompt 026." Every create/update also
(re-)registers the schedule with the live
:class:`~shared_core.scheduler.SchedulerManager` so it starts firing
immediately -- see ``app/scheduling/registrar.py``'s own docstring for
why a stable ``job_id`` makes this an idempotent upsert rather than a
leak, and ``app/core/factory.py``'s ``_lifespan`` for how every
already-active schedule is re-registered on process startup too.
"""

from __future__ import annotations

import contextlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context
from shared_core.scheduler import JobFn, JobNotFoundError, SchedulerManager

from app.api.deps import (
    CurrentUserId,
    ScheduleSvc,
    get_discovery_schedule_fn,
    get_scheduler_manager,
)
from app.models.discovery_schedule import DiscoverySchedule
from app.scheduling.registrar import register_schedule
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.schedule import (
    DiscoveryScheduleCreateRequest,
    DiscoveryScheduleResponse,
    DiscoveryScheduleUpdateRequest,
)

router = APIRouter(prefix="/discovery/schedules", tags=["Schedules"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(schedule: DiscoverySchedule) -> DiscoveryScheduleResponse:
    return DiscoveryScheduleResponse(
        id=schedule.id,
        organization_id=schedule.organization_id,
        profile_id=schedule.profile_id,
        name=schedule.name,
        schedule_type=schedule.schedule_type,
        cron_expression=schedule.cron_expression,
        interval_seconds=schedule.interval_seconds,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        is_enabled=schedule.is_enabled,
        priority=schedule.priority,
        concurrency_limit=schedule.concurrency_limit,
    )


def _cancel_registration(manager: SchedulerManager, schedule_id: UUID) -> None:
    """Best-effort cancel: a schedule that failed validation at register
    time (e.g. ``build_schedule`` raising ``ValueError``) was never
    actually registered, so "not found" here is expected, not an error.
    """
    with contextlib.suppress(JobNotFoundError):
        manager.cancel_job(str(schedule_id))


@router.get("", response_model=SuccessResponse[list[DiscoveryScheduleResponse]])
async def list_schedules(
    organization_id: UUID, schedules: ScheduleSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DiscoveryScheduleResponse]]:
    """List every discovery schedule defined for *organization_id*."""
    records = await schedules.list_for_org(organization_id)
    return SuccessResponse(
        message="Discovery schedules retrieved.",
        data=[_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[DiscoveryScheduleResponse], status_code=201)
async def create_schedule(
    body: DiscoveryScheduleCreateRequest,
    schedules: ScheduleSvc,
    _caller: CurrentUserId,
    manager: Annotated[SchedulerManager, Depends(get_scheduler_manager)],
    fn: Annotated[JobFn, Depends(get_discovery_schedule_fn)],
) -> SuccessResponse[DiscoveryScheduleResponse]:
    """Create a new discovery schedule and register it with the scheduler.

    Raises:
        ValueError: If *schedule_type* is ``CRON``/``INTERVAL`` and the
            field that type requires wasn't supplied.
    """
    schedule = await schedules.create(
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        name=body.name,
        schedule_type=body.schedule_type,
        cron_expression=body.cron_expression,
        interval_seconds=body.interval_seconds,
        next_run_at=body.next_run_at,
        maintenance_window=body.maintenance_window,
        retry_policy=body.retry_policy,
        priority=body.priority,
        concurrency_limit=body.concurrency_limit,
    )
    register_schedule(manager, schedule, fn)
    return SuccessResponse(
        message="Discovery schedule created.", data=_to_response(schedule), meta=_meta()
    )


@router.put("/{schedule_id}", response_model=SuccessResponse[DiscoveryScheduleResponse])
async def update_schedule(
    schedule_id: UUID,
    body: DiscoveryScheduleUpdateRequest,
    schedules: ScheduleSvc,
    _caller: CurrentUserId,
    manager: Annotated[SchedulerManager, Depends(get_scheduler_manager)],
    fn: Annotated[JobFn, Depends(get_discovery_schedule_fn)],
) -> SuccessResponse[DiscoveryScheduleResponse]:
    """Replace a discovery schedule's mutable fields and re-register it.

    A disabled schedule is unregistered instead of re-registered, so a
    caller flipping ``is_enabled=False`` reliably stops it firing.

    Raises:
        NotFoundError: If no such schedule exists.
        ValueError: If *schedule_type* is ``CRON``/``INTERVAL`` and the
            field that type requires wasn't supplied.
    """
    schedule = await schedules.update(
        schedule_id,
        name=body.name,
        schedule_type=body.schedule_type,
        cron_expression=body.cron_expression,
        interval_seconds=body.interval_seconds,
        next_run_at=body.next_run_at,
        is_enabled=body.is_enabled,
        maintenance_window=body.maintenance_window,
        retry_policy=body.retry_policy,
        priority=body.priority,
        concurrency_limit=body.concurrency_limit,
    )
    if schedule.is_enabled:
        register_schedule(manager, schedule, fn)
    else:
        _cancel_registration(manager, schedule_id)
    return SuccessResponse(
        message="Discovery schedule updated.", data=_to_response(schedule), meta=_meta()
    )


@router.delete("/{schedule_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_schedule(
    schedule_id: UUID,
    schedules: ScheduleSvc,
    _caller: CurrentUserId,
    manager: Annotated[SchedulerManager, Depends(get_scheduler_manager)],
) -> SuccessResponse[dict[str, bool]]:
    """Delete a discovery schedule and unregister it from the scheduler.

    Raises:
        NotFoundError: If no such schedule exists.
    """
    _cancel_registration(manager, schedule_id)
    await schedules.delete(schedule_id)
    return SuccessResponse(
        message="Discovery schedule deleted.", data={"success": True}, meta=_meta()
    )


__all__ = ["router"]
