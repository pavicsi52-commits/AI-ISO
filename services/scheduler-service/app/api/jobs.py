"""Job CRUD, lifecycle, triggers, dependencies, and retry policy."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    DependencySvc,
    ExecutionSvc,
    HistoryRepo,
    JobSvc,
    RetryPolicyRepo,
    TriggerSvc,
)
from app.models.enums import AuditAction, JobPriority, JobType, ScheduledJobStatus
from app.models.retry import JobRetryPolicy
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import (
    DependencyCreateRequest,
    DependencyResponse,
    JobCancelRequest,
    JobCreateRequest,
    JobExecutionResponse,
    JobHistoryResponse,
    JobResponse,
    JobRunResponse,
    JobScheduleResponse,
    JobUpdateRequest,
    RetryPolicyResponse,
    RetryPolicySetRequest,
    TriggerCreateRequest,
    TriggerEnabledRequest,
    TriggerResponse,
)

router = APIRouter(prefix="/scheduler/jobs", tags=["Jobs"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[JobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new job",
)
async def create_job(
    organization_id: UUID,
    body: JobCreateRequest,
    jobs: JobSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[JobResponse]:
    """Register a new job, directly ``ACTIVE``."""
    created = await jobs.create(
        organization_id,
        name=body.name,
        job_type=body.job_type,
        description=body.description,
        priority=body.priority,
        owner_id=body.owner_id,
        timezone=body.timezone,
        payload=body.payload,
        job_metadata=body.job_metadata,
        tags=body.tags,
        timeout_seconds=body.timeout_seconds,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.JOB_CREATED,
        entity_type="job",
        entity_id=created.id,
        entity_reference=created.name,
        actor_id=str(caller),
        summary=f"Registered job {created.name!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(created), message="Job registered."
    )


@router.get("", response_model=SuccessResponse[list[JobResponse]], summary="List jobs")
async def list_jobs(
    organization_id: UUID,
    jobs: JobSvc,
    status_filter: Annotated[ScheduledJobStatus | None, Query(alias="status")] = None,
    job_type: Annotated[JobType | None, Query()] = None,
    priority: Annotated[JobPriority | None, Query()] = None,
    owner_id: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[JobResponse]]:
    """Jobs matching a caller's filters."""
    rows = await jobs.list_jobs(
        organization_id,
        status=status_filter,
        job_type=job_type,
        priority=priority,
        owner_id=owner_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[JobResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} job(s).",
    )


@router.get("/{job_id}", response_model=SuccessResponse[JobResponse], summary="Read one job")
async def get_job(
    organization_id: UUID, job_id: UUID, jobs: JobSvc
) -> SuccessResponse[JobResponse]:
    """One job."""
    found = await jobs.get(organization_id, job_id)
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(found), message="Job read."
    )


@router.put("/{job_id}", response_model=SuccessResponse[JobResponse], summary="Edit a job")
async def update_job(
    organization_id: UUID,
    job_id: UUID,
    body: JobUpdateRequest,
    jobs: JobSvc,
    caller: CurrentUserId,
) -> SuccessResponse[JobResponse]:
    """Edit a job's own editable fields."""
    updated = await jobs.update(
        organization_id, job_id, actor_id=str(caller), **body.model_dump(exclude_unset=True)
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(updated), message="Job updated."
    )


@router.delete("/{job_id}", response_model=SuccessResponse[JobResponse], summary="Delete a job")
async def delete_job(
    organization_id: UUID, job_id: UUID, jobs: JobSvc, audit: AuditSvc, caller: CurrentUserId
) -> SuccessResponse[JobResponse]:
    """Delete a job for good."""
    updated = await jobs.delete(organization_id, job_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.JOB_DELETED,
        entity_type="job",
        entity_id=job_id,
        actor_id=str(caller),
        summary=f"Deleted job {updated.name!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(updated), message="Job deleted."
    )


@router.post(
    "/{job_id}/run",
    response_model=SuccessResponse[JobRunResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch a job immediately",
)
async def run_job(
    organization_id: UUID,
    job_id: UUID,
    executions: ExecutionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[JobRunResponse]:
    """Dispatch one execution of a job right now, regardless of its schedule."""
    execution = await executions.dispatch(organization_id, job_id, trigger_source="manual")
    await audit.record(
        organization_id,
        action=AuditAction.JOB_EXECUTED,
        entity_type="job",
        entity_id=job_id,
        actor_id=str(caller),
        summary=f"Manually dispatched job {job_id}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=JobRunResponse(execution=JobExecutionResponse.model_validate(execution)),
        message="Job dispatched.",
    )


@router.post("/{job_id}/pause", response_model=SuccessResponse[JobResponse], summary="Pause a job")
async def pause_job(
    organization_id: UUID, job_id: UUID, jobs: JobSvc, audit: AuditSvc, caller: CurrentUserId
) -> SuccessResponse[JobResponse]:
    """Pause a job -- temporarily, resumable via ``/resume``."""
    updated = await jobs.pause(organization_id, job_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.JOB_PAUSED,
        entity_type="job",
        entity_id=job_id,
        actor_id=str(caller),
        summary=f"Paused job {updated.name!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(updated), message="Job paused."
    )


@router.post(
    "/{job_id}/resume", response_model=SuccessResponse[JobResponse], summary="Resume a paused job"
)
async def resume_job(
    organization_id: UUID, job_id: UUID, jobs: JobSvc, audit: AuditSvc, caller: CurrentUserId
) -> SuccessResponse[JobResponse]:
    """Resume a paused job."""
    updated = await jobs.resume(organization_id, job_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.JOB_RESUMED,
        entity_type="job",
        entity_id=job_id,
        actor_id=str(caller),
        summary=f"Resumed job {updated.name!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(updated), message="Job resumed."
    )


@router.post(
    "/{job_id}/cancel", response_model=SuccessResponse[JobResponse], summary="Cancel a job for good"
)
async def cancel_job(
    organization_id: UUID,
    job_id: UUID,
    body: JobCancelRequest,
    jobs: JobSvc,
    executions: ExecutionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[JobResponse]:
    """Stop a job for good -- disabled, and any execution still in flight is cancelled."""
    await executions.cancel_open_for_job(organization_id, job_id)
    updated = await jobs.cancel(organization_id, job_id, actor_id=str(caller), reason=body.reason)
    await audit.record(
        organization_id,
        action=AuditAction.JOB_CANCELLED,
        entity_type="job",
        entity_id=job_id,
        actor_id=str(caller),
        summary=f"Cancelled job {updated.name!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=JobResponse.model_validate(updated), message="Job cancelled."
    )


@router.get(
    "/{job_id}/schedule",
    response_model=SuccessResponse[JobScheduleResponse],
    summary="Read a job's computed schedule state",
)
async def get_job_schedule(
    organization_id: UUID, job_id: UUID, triggers: TriggerSvc
) -> SuccessResponse[JobScheduleResponse]:
    """The materialized next-due state a sweep actually polls."""
    schedule = await triggers.recompute_schedule(organization_id, job_id)
    return SuccessResponse(
        meta=_meta(), data=JobScheduleResponse.model_validate(schedule), message="Schedule read."
    )


@router.get(
    "/{job_id}/history",
    response_model=SuccessResponse[list[JobHistoryResponse]],
    summary="Read a job's status history",
)
async def get_job_history(
    organization_id: UUID, job_id: UUID, history: HistoryRepo
) -> SuccessResponse[list[JobHistoryResponse]]:
    """Every status transition a job definition went through."""
    rows = await history.list_for_job(organization_id, job_id)
    return SuccessResponse(
        meta=_meta(),
        data=[JobHistoryResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} transition(s).",
    )


# ---- triggers -----------------------------------------------------------------


@router.post(
    "/{job_id}/triggers",
    response_model=SuccessResponse[TriggerResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Attach a trigger to a job",
)
async def add_trigger(
    organization_id: UUID, job_id: UUID, body: TriggerCreateRequest, triggers: TriggerSvc
) -> SuccessResponse[TriggerResponse]:
    """Attach a new trigger, and recompute the job's schedule."""
    created = await triggers.add_trigger(
        organization_id,
        job_id,
        trigger_type=body.trigger_type,
        cron_expression=body.cron_expression,
        run_at=body.run_at,
        interval_seconds=body.interval_seconds,
        calendar_rule=body.calendar_rule,
        calendar_config=body.calendar_config,
        event_name=body.event_name,
        description=body.description,
        enabled=body.enabled,
    )
    return SuccessResponse(
        meta=_meta(), data=TriggerResponse.model_validate(created), message="Trigger attached."
    )


@router.get(
    "/{job_id}/triggers",
    response_model=SuccessResponse[list[TriggerResponse]],
    summary="List a job's triggers",
)
async def list_triggers(
    organization_id: UUID, job_id: UUID, triggers: TriggerSvc
) -> SuccessResponse[list[TriggerResponse]]:
    """Every trigger registered for one job."""
    rows = await triggers.list_triggers(organization_id, job_id)
    return SuccessResponse(
        meta=_meta(),
        data=[TriggerResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} trigger(s).",
    )


@router.put(
    "/triggers/{trigger_id}/enabled",
    response_model=SuccessResponse[TriggerResponse],
    summary="Enable or disable a trigger",
)
async def set_trigger_enabled(
    organization_id: UUID, trigger_id: UUID, body: TriggerEnabledRequest, triggers: TriggerSvc
) -> SuccessResponse[TriggerResponse]:
    """Enable or disable a trigger, and recompute its job's schedule."""
    updated = await triggers.set_enabled(organization_id, trigger_id, enabled=body.enabled)
    return SuccessResponse(
        meta=_meta(), data=TriggerResponse.model_validate(updated), message="Trigger updated."
    )


@router.delete(
    "/triggers/{trigger_id}", response_model=SuccessResponse[None], summary="Remove a trigger"
)
async def remove_trigger(
    organization_id: UUID, trigger_id: UUID, triggers: TriggerSvc
) -> SuccessResponse[None]:
    """Remove a trigger, and recompute its job's schedule."""
    await triggers.remove(organization_id, trigger_id)
    return SuccessResponse(meta=_meta(), data=None, message="Trigger removed.")


# ---- dependencies -----------------------------------------------------------


@router.post(
    "/{job_id}/dependencies",
    response_model=SuccessResponse[DependencyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a dependency to a job",
)
async def add_dependency(
    organization_id: UUID, job_id: UUID, body: DependencyCreateRequest, dependencies: DependencySvc
) -> SuccessResponse[DependencyResponse]:
    """Register *job_id* as depending on *parent_job_id*."""
    created = await dependencies.add_dependency(
        organization_id,
        parent_job_id=body.parent_job_id,
        child_job_id=job_id,
        dependency_type=body.dependency_type,
        condition=body.condition,
    )
    return SuccessResponse(
        meta=_meta(), data=DependencyResponse.model_validate(created), message="Dependency added."
    )


@router.get(
    "/{job_id}/dependencies",
    response_model=SuccessResponse[list[DependencyResponse]],
    summary="List a job's dependencies",
)
async def list_dependencies(
    organization_id: UUID, job_id: UUID, dependencies: DependencySvc
) -> SuccessResponse[list[DependencyResponse]]:
    """Every dependency naming this job as the dependent (child) side."""
    rows = await dependencies.list_for_job(organization_id, job_id)
    return SuccessResponse(
        meta=_meta(),
        data=[DependencyResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} dependency(ies).",
    )


@router.delete(
    "/dependencies/{dependency_id}",
    response_model=SuccessResponse[None],
    summary="Remove a dependency",
)
async def remove_dependency(
    organization_id: UUID, dependency_id: UUID, dependencies: DependencySvc
) -> SuccessResponse[None]:
    """Remove a dependency edge."""
    await dependencies.remove(organization_id, dependency_id)
    return SuccessResponse(meta=_meta(), data=None, message="Dependency removed.")


# ---- retry policy -------------------------------------------------------------


@router.put(
    "/{job_id}/retry-policy",
    response_model=SuccessResponse[RetryPolicyResponse],
    summary="Set a job's retry policy",
)
async def set_retry_policy(
    organization_id: UUID,
    job_id: UUID,
    body: RetryPolicySetRequest,
    retry_policies: RetryPolicyRepo,
) -> SuccessResponse[RetryPolicyResponse]:
    """Create or replace a job's own retry policy."""
    existing = await retry_policies.get_for_job(organization_id, job_id)
    row = existing or JobRetryPolicy(organization_id=organization_id, job_id=job_id)
    row.retry_type = body.retry_type
    row.max_attempts = body.max_attempts
    row.base_delay_seconds = body.base_delay_seconds
    row.max_delay_seconds = body.max_delay_seconds
    row.retry_conditions = body.retry_conditions
    row.dead_letter_enabled = body.dead_letter_enabled
    saved = await (retry_policies.update(row) if existing else retry_policies.create(row))
    return SuccessResponse(
        meta=_meta(), data=RetryPolicyResponse.model_validate(saved), message="Retry policy set."
    )


@router.get(
    "/{job_id}/retry-policy",
    response_model=SuccessResponse[RetryPolicyResponse | None],
    summary="Read a job's retry policy",
)
async def get_retry_policy(
    organization_id: UUID,
    job_id: UUID,
    retry_policies: RetryPolicyRepo,
) -> SuccessResponse[RetryPolicyResponse | None]:
    """A job's own retry policy, if one has been configured."""
    found = await retry_policies.get_for_job(organization_id, job_id)
    data = RetryPolicyResponse.model_validate(found) if found else None
    return SuccessResponse(
        meta=_meta(),
        data=data,
        message="Policy found." if found else "No policy configured; platform default applies.",
    )


__all__ = ["router"]
