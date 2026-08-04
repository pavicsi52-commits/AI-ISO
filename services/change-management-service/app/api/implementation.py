"""Implementation task, run, and validation endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ImplementationSvc
from app.models.enums import AuditAction
from app.schemas.change import (
    ImplementationResponse,
    TaskCreateRequest,
    TaskResponse,
    ValidationRecordRequest,
    ValidationResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Implementation"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/changes/{change_id}/tasks",
    response_model=SuccessResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add an implementation task",
)
async def add_task(
    organization_id: UUID, change_id: UUID, body: TaskCreateRequest, impl: ImplementationSvc
) -> SuccessResponse[TaskResponse]:
    """Add one implementation task to a change."""
    created = await impl.add_task(
        organization_id,
        change_id,
        title=body.title,
        description=body.description,
        assignee_id=body.assignee_id,
    )
    return SuccessResponse(
        meta=_meta(), data=TaskResponse.model_validate(created), message="Task added."
    )


@router.get(
    "/changes/{change_id}/tasks",
    response_model=SuccessResponse[list[TaskResponse]],
    summary="List a change's implementation tasks",
)
async def list_tasks(
    organization_id: UUID, change_id: UUID, impl: ImplementationSvc
) -> SuccessResponse[list[TaskResponse]]:
    """Every task for one change, in execution order."""
    rows = await impl.list_tasks(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[TaskResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} task(s).",
    )


@router.post(
    "/tasks/{task_id}/complete",
    response_model=SuccessResponse[TaskResponse],
    summary="Mark a task done",
)
async def complete_task(
    organization_id: UUID, task_id: UUID, impl: ImplementationSvc
) -> SuccessResponse[TaskResponse]:
    """Mark a task done."""
    updated = await impl.complete_task(organization_id, task_id)
    return SuccessResponse(
        meta=_meta(), data=TaskResponse.model_validate(updated), message="Task completed."
    )


@router.post(
    "/tasks/{task_id}/fail",
    response_model=SuccessResponse[TaskResponse],
    summary="Mark a task failed",
)
async def fail_task(
    organization_id: UUID, task_id: UUID, impl: ImplementationSvc
) -> SuccessResponse[TaskResponse]:
    """Mark a task failed."""
    updated = await impl.fail_task(organization_id, task_id)
    return SuccessResponse(
        meta=_meta(), data=TaskResponse.model_validate(updated), message="Task marked failed."
    )


@router.post(
    "/changes/{change_id}/implementation/start",
    response_model=SuccessResponse[ImplementationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Begin implementing a ready change",
)
async def start_implementation(
    organization_id: UUID,
    change_id: UUID,
    impl: ImplementationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ImplementationResponse]:
    """Begin implementation."""
    created = await impl.start(organization_id, change_id, started_by=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.IMPLEMENTATION_STARTED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"Implementation started for change {change_id}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=ImplementationResponse.model_validate(created),
        message="Implementation started.",
    )


@router.post(
    "/changes/{change_id}/implementation/validate",
    response_model=SuccessResponse[ImplementationResponse],
    summary="Move a change from implementation into post-change validation",
)
async def move_to_validation(
    organization_id: UUID, change_id: UUID, impl: ImplementationSvc, caller: CurrentUserId
) -> SuccessResponse[ImplementationResponse]:
    """Move into the post-change validation phase. Refuses while any task is unfinished."""
    updated = await impl.move_to_validation(organization_id, change_id, actor_id=caller)
    return SuccessResponse(
        meta=_meta(),
        data=ImplementationResponse.model_validate(updated),
        message="Moved to validation.",
    )


@router.post(
    "/changes/{change_id}/implementation/complete",
    response_model=SuccessResponse[ImplementationResponse],
    summary="Complete a change that has passed validation",
)
async def complete_implementation(
    organization_id: UUID,
    change_id: UUID,
    impl: ImplementationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ImplementationResponse]:
    """Complete implementation. Refuses while any gate validation has failed."""
    updated = await impl.complete(organization_id, change_id, actor_id=caller)
    await audit.record(
        organization_id,
        action=AuditAction.IMPLEMENTATION_COMPLETED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"Implementation completed for change {change_id}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=ImplementationResponse.model_validate(updated),
        message="Implementation completed.",
    )


@router.post(
    "/changes/{change_id}/validations",
    response_model=SuccessResponse[ValidationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a validation run",
)
async def record_validation(
    organization_id: UUID,
    change_id: UUID,
    body: ValidationRecordRequest,
    impl: ImplementationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ValidationResponse]:
    """Record one validation run against a change."""
    created = await impl.record_validation(
        organization_id,
        change_id,
        kind=body.kind,
        status=body.status,
        summary=body.summary,
        is_gate=body.is_gate,
        ran_by=body.ran_by,
        evidence=body.evidence,
    )
    await audit.record(
        organization_id,
        action=AuditAction.VALIDATION_RECORDED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"Recorded a {body.kind!s} validation: {body.status!s}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=ValidationResponse.model_validate(created),
        message="Validation recorded.",
    )


@router.get(
    "/changes/{change_id}/validations",
    response_model=SuccessResponse[list[ValidationResponse]],
    summary="List a change's validation runs",
)
async def list_validations(
    organization_id: UUID, change_id: UUID, impl: ImplementationSvc
) -> SuccessResponse[list[ValidationResponse]]:
    """Every validation run for one change."""
    rows = await impl.list_validations(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ValidationResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} validation(s).",
    )


__all__ = ["router"]
