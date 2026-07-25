"""``/automation/jobs`` and its ``execute``/``cancel``/``pause``/
``resume`` actions. Per docs/040 REST list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, CurrentUserToken, ExecutionSvc, JobSvc, QueueProducerDep
from app.models.automation_execution import AutomationExecution
from app.models.automation_job import AutomationJob
from app.schemas.execution import AutomationExecutionRequest, AutomationExecutionResponse
from app.schemas.job import (
    AutomationJobCreateRequest,
    AutomationJobResponse,
    AutomationJobUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.workers.execution_worker import EXECUTION_QUEUE_NAME

router = APIRouter(prefix="/automation/jobs", tags=["Automation Jobs"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def job_to_response(job: AutomationJob) -> AutomationJobResponse:
    return AutomationJobResponse(
        id=job.id,
        organization_id=job.organization_id,
        project_id=job.project_id,
        name=job.name,
        description=job.description,
        automation_type=job.automation_type,
        playbook_type=job.playbook_type,
        status=job.status,
        execution_mode=job.execution_mode,
        content=job.content,
        target_selector=job.target_selector,
        variables=job.variables,
        tags=job.tags,
        timeout_seconds=job.timeout_seconds,
        owner_id=job.owner_id,
    )


def execution_to_response(execution: AutomationExecution) -> AutomationExecutionResponse:
    return AutomationExecutionResponse(
        id=execution.id,
        organization_id=execution.organization_id,
        job_id=execution.job_id,
        execution_plan_id=execution.execution_plan_id,
        status=execution.status,
        execution_mode=execution.execution_mode,
        triggered_by=execution.triggered_by,
        variables=execution.variables,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        timeout_seconds=execution.timeout_seconds,
        error_message=execution.error_message,
        created_at=execution.created_at,
    )


@router.get("", response_model=SuccessResponse[list[AutomationJobResponse]])
async def list_jobs(
    organization_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AutomationJobResponse]]:
    """List every automation job in *organization_id*."""
    records = await jobs.list_for_org(organization_id)
    data = [job_to_response(record) for record in records]
    return SuccessResponse(message="Automation jobs retrieved.", data=data, meta=_meta())


@router.get("/{job_id}", response_model=SuccessResponse[AutomationJobResponse])
async def get_job(
    job_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationJobResponse]:
    """Return one automation job.

    Raises:
        NotFoundError: If no such job exists.
    """
    job = await jobs.get_by_id(job_id)
    return SuccessResponse(
        message="Automation job retrieved.", data=job_to_response(job), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[AutomationJobResponse], status_code=201)
async def create_job(
    body: AutomationJobCreateRequest, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[AutomationJobResponse]:
    """Define a new automation job ("Create")."""
    job = await jobs.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        automation_type=body.automation_type,
        playbook_type=body.playbook_type,
        execution_mode=body.execution_mode,
        content=body.content,
        target_selector=body.target_selector,
        variables=body.variables,
        tags=body.tags,
        timeout_seconds=body.timeout_seconds,
        owner_id=body.owner_id,
        created_by=caller,
    )
    return SuccessResponse(
        message="Automation job created.", data=job_to_response(job), meta=_meta()
    )


@router.put("/{job_id}", response_model=SuccessResponse[AutomationJobResponse])
async def update_job(
    job_id: UUID, body: AutomationJobUpdateRequest, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[AutomationJobResponse]:
    """Replace an automation job's mutable fields ("Update")."""
    job = await jobs.update(
        job_id,
        actor_id=caller,
        name=body.name,
        description=body.description,
        status=body.status,
        automation_type=body.automation_type,
        playbook_type=body.playbook_type,
        execution_mode=body.execution_mode,
        content=body.content,
        target_selector=body.target_selector,
        variables=body.variables,
        tags=body.tags,
        timeout_seconds=body.timeout_seconds,
        owner_id=body.owner_id,
    )
    return SuccessResponse(
        message="Automation job updated.", data=job_to_response(job), meta=_meta()
    )


@router.delete("/{job_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_job(
    job_id: UUID, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete an automation job ("Delete")."""
    await jobs.delete(job_id, actor_id=caller)
    return SuccessResponse(message="Automation job deleted.", data={"success": True}, meta=_meta())


@router.post(
    "/{job_id}/execute",
    response_model=SuccessResponse[AutomationExecutionResponse],
    status_code=201,
)
async def execute_job(
    job_id: UUID,
    body: AutomationExecutionRequest,
    executions: ExecutionSvc,
    caller: CurrentUserId,
    caller_token: CurrentUserToken,
    queue_producer: QueueProducerDep,
) -> SuccessResponse[AutomationExecutionResponse]:
    """Create a new execution of an automation job and enqueue it for
    dispatch ("Execution"/"Async Execution") -- the actual run happens in
    :mod:`app.workers.execution_worker`, not on this request.
    """
    execution = await executions.create_execution(
        job_id,
        target_ids=body.target_ids,
        variables=body.variables,
        execution_mode=body.execution_mode,
        timeout_seconds=body.timeout_seconds,
        triggered_by=caller,
    )
    await queue_producer.publish(
        EXECUTION_QUEUE_NAME,
        {"execution_id": str(execution.id), "caller_token": caller_token},
    )
    return SuccessResponse(
        message="Automation job execution enqueued.",
        data=execution_to_response(execution),
        meta=_meta(),
    )


@router.post("/{job_id}/cancel", response_model=SuccessResponse[AutomationExecutionResponse])
async def cancel_job(
    job_id: UUID, executions: ExecutionSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationExecutionResponse]:
    """Cancel an automation job's currently active execution ("Cancel")."""
    execution = await executions.cancel_job_execution(job_id)
    return SuccessResponse(
        message="Automation job execution cancelled.",
        data=execution_to_response(execution),
        meta=_meta(),
    )


@router.post("/{job_id}/pause", response_model=SuccessResponse[AutomationExecutionResponse])
async def pause_job(
    job_id: UUID, executions: ExecutionSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationExecutionResponse]:
    """Pause an automation job's currently running execution ("Pause")."""
    execution = await executions.pause_job_execution(job_id)
    return SuccessResponse(
        message="Automation job execution paused.",
        data=execution_to_response(execution),
        meta=_meta(),
    )


@router.post("/{job_id}/resume", response_model=SuccessResponse[AutomationExecutionResponse])
async def resume_job(
    job_id: UUID,
    executions: ExecutionSvc,
    _caller: CurrentUserId,
    caller_token: CurrentUserToken,
    queue_producer: QueueProducerDep,
) -> SuccessResponse[AutomationExecutionResponse]:
    """Resume an automation job's paused execution and re-enqueue it for
    dispatch ("Resume").
    """
    execution = await executions.resume_job_execution(job_id)
    await queue_producer.publish(
        EXECUTION_QUEUE_NAME,
        {"execution_id": str(execution.id), "caller_token": caller_token},
    )
    return SuccessResponse(
        message="Automation job execution resumed.",
        data=execution_to_response(execution),
        meta=_meta(),
    )


__all__ = ["execution_to_response", "job_to_response", "router"]
