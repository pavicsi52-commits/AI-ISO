"""Failures and manual recovery."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, RecoverySvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import FailureResponse, RecoverFailureRequest

router = APIRouter(prefix="/scheduler/failures", tags=["Failures"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[list[FailureResponse]],
    summary="List unrecovered terminal failures",
)
async def list_unrecovered_failures(
    organization_id: UUID, recovery: RecoverySvc
) -> SuccessResponse[list[FailureResponse]]:
    """Every terminal failure nobody has recovered yet."""
    rows = await recovery.list_unrecovered(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[FailureResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} unrecovered failure(s).",
    )


@router.post(
    "/{failure_id}/recover",
    response_model=SuccessResponse[FailureResponse],
    summary="Manually recover a failure",
)
async def recover_failure(
    organization_id: UUID,
    failure_id: UUID,
    body: RecoverFailureRequest,
    recovery: RecoverySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FailureResponse]:
    """Recover a terminal failure, optionally dispatching a fresh attempt."""
    updated = await recovery.recover(
        organization_id,
        failure_id,
        action=body.action,
        recovered_by=body.recovered_by or str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.JOB_RECOVERED,
        entity_type="job_failure",
        entity_id=failure_id,
        actor_id=str(caller),
        summary=f"Recovered failure {failure_id} via {body.action!s}.",
    )
    return SuccessResponse(
        meta=_meta(), data=FailureResponse.model_validate(updated), message="Failure recovered."
    )


__all__ = ["router"]
