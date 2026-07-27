"""``/validations`` and its ``execute``/``cancel`` actions. Per
docs/043 REST list.

The full-lifecycle resource (CRUD + ``execute``/``cancel``) for
:class:`~app.models.validation_profile.ValidationProfile` -- see
``app/schemas/profile.py``'s own docstring for why this router and
``app/api/profiles.py``'s own ``/validation-profiles`` both front the
identical underlying service. ``execute``/``cancel`` act on the
profile's own most recent, still-active execution, the same
interpretation docs/040/042's identically-shaped
``/workflows/{id}/execute``/``/pause``/``/cancel`` endpoints already
established for this exact phrasing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    CurrentUserToken,
    ExecutionSvc,
    ProfileSvc,
    QueueProducerDep,
    TargetSvc,
)
from app.models.validation_execution import ValidationExecution
from app.models.validation_profile import ValidationProfile
from app.schemas.execution import ValidationExecuteRequest, ValidationExecutionResponse
from app.schemas.profile import (
    ValidationProfileCreateRequest,
    ValidationProfileResponse,
    ValidationProfileUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.workers.execution_worker import EXECUTION_QUEUE_NAME

router = APIRouter(prefix="/validations", tags=["Validations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def profile_to_response(profile: ValidationProfile) -> ValidationProfileResponse:
    return ValidationProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        project_id=profile.project_id,
        name=profile.name,
        description=profile.description,
        profile_type=profile.profile_type,
        target_types=profile.target_types,
        check_ids=profile.check_ids,
        concurrency_strategy=profile.concurrency_strategy,
        scoring_weights=profile.scoring_weights,
        tags=profile.tags,
        owner=profile.owner,
        current_version_number=profile.current_version_number,
    )


def execution_to_response(execution: ValidationExecution) -> ValidationExecutionResponse:
    return ValidationExecutionResponse(
        id=execution.id,
        organization_id=execution.organization_id,
        project_id=execution.project_id,
        profile_id=execution.profile_id,
        target_ids=execution.target_ids,
        trigger_type=execution.trigger_type,
        concurrency_strategy=execution.concurrency_strategy,
        status=execution.status,
        triggered_by=execution.triggered_by,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        error_message=execution.error_message,
    )


@router.get("", response_model=SuccessResponse[list[ValidationProfileResponse]])
async def list_validations(
    organization_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationProfileResponse]]:
    """List every validation profile in *organization_id*."""
    records = await profiles.list_for_org(organization_id)
    data = [profile_to_response(record) for record in records]
    return SuccessResponse(message="Validation profiles retrieved.", data=data, meta=_meta())


@router.get("/{validation_id}", response_model=SuccessResponse[ValidationProfileResponse])
async def get_validation(
    validation_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationProfileResponse]:
    """Return one validation profile.

    Raises:
        NotFoundError: If no such profile exists.
    """
    profile = await profiles.get_by_id(validation_id)
    return SuccessResponse(
        message="Validation profile retrieved.", data=profile_to_response(profile), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ValidationProfileResponse], status_code=201)
async def create_validation(
    body: ValidationProfileCreateRequest, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationProfileResponse]:
    """Create a new validation profile ("Create")."""
    profile = await profiles.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        target_types=body.target_types,
        check_ids=body.check_ids,
        concurrency_strategy=body.concurrency_strategy,
        scoring_weights=body.scoring_weights,
        tags=body.tags,
        owner=body.owner,
    )
    return SuccessResponse(
        message="Validation profile created.", data=profile_to_response(profile), meta=_meta()
    )


@router.put("/{validation_id}", response_model=SuccessResponse[ValidationProfileResponse])
async def update_validation(
    validation_id: UUID,
    body: ValidationProfileUpdateRequest,
    profiles: ProfileSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[ValidationProfileResponse]:
    """Replace a profile's own metadata and bump its own version ("Update").

    Raises:
        NotFoundError: If no such profile exists.
    """
    profile = await profiles.update(
        validation_id,
        name=body.name,
        description=body.description,
        target_types=body.target_types,
        check_ids=body.check_ids,
        concurrency_strategy=body.concurrency_strategy,
        scoring_weights=body.scoring_weights,
        tags=body.tags,
        owner=body.owner,
    )
    return SuccessResponse(
        message="Validation profile updated.", data=profile_to_response(profile), meta=_meta()
    )


@router.delete("/{validation_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_validation(
    validation_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a validation profile ("Delete")."""
    await profiles.delete(validation_id)
    return SuccessResponse(
        message="Validation profile deleted.", data={"success": True}, meta=_meta()
    )


@router.post(
    "/{validation_id}/execute",
    response_model=SuccessResponse[ValidationExecutionResponse],
    status_code=201,
)
async def execute_validation(
    validation_id: UUID,
    body: ValidationExecuteRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    execution: ExecutionSvc,
    caller: CurrentUserId,
    caller_token: CurrentUserToken,
    queue_producer: QueueProducerDep,
) -> SuccessResponse[ValidationExecutionResponse]:
    """Create a new execution of a validation profile and enqueue it for
    background dispatch ("Execute") -- the actual run happens in
    :mod:`app.workers.execution_worker`, not on this request.

    Raises:
        NotFoundError: If no such profile exists.
    """
    profile = await profiles.get_by_id(validation_id)
    target_rows = [
        await targets.get_or_create(
            organization_id=profile.organization_id,
            project_id=profile.project_id,
            target_type=target.target_type,
            external_id=target.external_id,
            name=target.name,
            target_metadata=target.target_metadata,
        )
        for target in body.targets
    ]
    new_execution = await execution.create(
        organization_id=profile.organization_id,
        project_id=profile.project_id,
        profile_id=profile.id,
        target_ids=[target.id for target in target_rows],
        concurrency_strategy=body.concurrency_strategy or profile.concurrency_strategy,
        triggered_by=caller,
    )
    await queue_producer.publish(
        EXECUTION_QUEUE_NAME,
        {"execution_id": str(new_execution.id), "caller_token": caller_token},
    )
    return SuccessResponse(
        message="Validation execution enqueued.",
        data=execution_to_response(new_execution),
        meta=_meta(),
    )


@router.post("/{validation_id}/cancel", response_model=SuccessResponse[ValidationExecutionResponse])
async def cancel_validation(
    validation_id: UUID, execution: ExecutionSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationExecutionResponse]:
    """Record caller intent to cancel *validation_id*'s own active execution ("Cancel")."""
    active = await execution.get_active_for_profile(validation_id)
    cancelled = await execution.cancel(active.id)
    return SuccessResponse(
        message="Validation execution cancelled.",
        data=execution_to_response(cancelled),
        meta=_meta(),
    )


__all__ = ["execution_to_response", "profile_to_response", "router"]
