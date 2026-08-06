"""Signing-secret management (docs/057 "SIGNATURE MANAGEMENT")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, SignatureSvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import SignatureCreateRequest, SignatureResponse, SignatureRotateRequest

router = APIRouter(prefix="/webhooks/signatures", tags=["Signatures"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[SignatureResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a signing secret",
)
async def create_signature(
    organization_id: UUID, body: SignatureCreateRequest, signatures: SignatureSvc
) -> SuccessResponse[SignatureResponse]:
    """Register the first signing secret for an endpoint. The raw secret is never stored."""
    created = await signatures.create(
        organization_id, endpoint_id=body.endpoint_id, secret=body.secret, algorithm=body.algorithm
    )
    return SuccessResponse(
        message="Signing secret created.", data=SignatureResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/rotate", response_model=SuccessResponse[SignatureResponse], summary="Rotate a signing secret"
)
async def rotate_signature(
    organization_id: UUID,
    body: SignatureRotateRequest,
    signatures: SignatureSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SignatureResponse]:
    """Rotate an endpoint's own signing secret, with an overlap window for the old one."""
    rotated = await signatures.rotate(
        organization_id,
        endpoint_id=body.endpoint_id,
        new_secret=body.new_secret,
        overlap_hours=body.overlap_hours,
    )
    await audit.record(
        organization_id,
        action=AuditAction.SECRET_ROTATED,
        entity_type="signature",
        entity_id=rotated.id,
        actor_id=str(caller),
        summary=f"Rotated signing secret for endpoint {body.endpoint_id}.",
    )
    return SuccessResponse(
        message="Signing secret rotated.", data=SignatureResponse.model_validate(rotated), meta=_meta()
    )


__all__ = ["router"]
