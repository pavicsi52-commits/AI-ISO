"""``GET /validation/remediation``. Per docs/043 REST list.

``POST`` (suggest a remediation) and ``POST .../apply`` have no REST
list entry of their own -- added directly, matching every prior
AI-IOS service's own "required capability, no REST list entry"
precedent, since a caller must be able to record a suggestion before
there is anything for ``GET`` to list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RemediationSvc
from app.models.enums import RemediationActionType
from app.models.validation_remediation import ValidationRemediation
from app.schemas.remediation import ValidationRemediationResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/validation/remediation", tags=["Remediation"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def remediation_to_response(remediation: ValidationRemediation) -> ValidationRemediationResponse:
    return ValidationRemediationResponse(
        id=remediation.id,
        organization_id=remediation.organization_id,
        failure_id=remediation.failure_id,
        action_type=remediation.action_type,
        description=remediation.description,
        automation_job_key=remediation.automation_job_key,
        playbook_key=remediation.playbook_key,
        workflow_key=remediation.workflow_key,
        knowledge_base_url=remediation.knowledge_base_url,
        is_applied=remediation.is_applied,
        applied_at=remediation.applied_at,
        applied_by=remediation.applied_by,
    )


@router.get("", response_model=SuccessResponse[list[ValidationRemediationResponse]])
async def list_remediation(
    organization_id: UUID, remediation: RemediationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationRemediationResponse]]:
    """List every remediation suggestion for *organization_id* ("Generate")."""
    records = await remediation.list_for_org(organization_id)
    data = [remediation_to_response(record) for record in records]
    return SuccessResponse(message="Validation remediation retrieved.", data=data, meta=_meta())


@router.post(
    "/{failure_id}",
    response_model=SuccessResponse[ValidationRemediationResponse],
    status_code=201,
)
async def suggest_remediation(
    failure_id: UUID,
    organization_id: UUID,
    action_type: RemediationActionType,
    description: str,
    remediation: RemediationSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[ValidationRemediationResponse]:
    """Record a new remediation suggestion for a known failure."""
    record = await remediation.suggest(
        organization_id=organization_id,
        failure_id=failure_id,
        action_type=action_type,
        description=description,
    )
    return SuccessResponse(
        message="Validation remediation suggested.",
        data=remediation_to_response(record),
        meta=_meta(),
    )


@router.post(
    "/{remediation_id}/apply", response_model=SuccessResponse[ValidationRemediationResponse]
)
async def apply_remediation(
    remediation_id: UUID, remediation: RemediationSvc, caller: CurrentUserId
) -> SuccessResponse[ValidationRemediationResponse]:
    """Record that a caller has applied a suggested remediation elsewhere.

    Raises:
        NotFoundError: If no such remediation exists.
    """
    record = await remediation.mark_applied(remediation_id, applied_by=caller)
    return SuccessResponse(
        message="Validation remediation marked applied.",
        data=remediation_to_response(record),
        meta=_meta(),
    )


__all__ = ["remediation_to_response", "router"]
