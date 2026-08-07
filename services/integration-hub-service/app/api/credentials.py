"""Connector credential management (docs/058 "CREDENTIAL MANAGEMENT")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, ConnectorSvc, CredentialSvc, CurrentUserId
from app.models.enums import AuditAction
from app.schemas.hub import CredentialAssignRequest, CredentialResponse, CredentialRotateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations/credentials", tags=["Credentials"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[CredentialResponse],
    status_code=201,
    summary="Assign a credential",
)
async def assign_credential(
    organization_id: UUID,
    body: CredentialAssignRequest,
    connectors: ConnectorSvc,
    credentials: CredentialSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[CredentialResponse]:
    """Assign a credential to a connector.

    Confirms *body.connector_id* actually belongs to *organization_id*
    first -- a credential row is not directly reachable by id from
    outside this organization, so without this check an organization
    could assign a credential onto another organization's own connector.
    """
    await connectors.get(organization_id, body.connector_id)
    created = await credentials.assign(
        organization_id,
        connector_id=body.connector_id,
        credential_type=body.credential_type,
        secret_ref=body.secret_ref,
        raw_value=body.raw_value,
        refresh_value=body.refresh_value,
        expires_at=body.expires_at,
        owner_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.CREDENTIAL_ASSIGNED,
        entity_type="credential",
        entity_id=created.id,
        actor_id=str(caller),
        summary=(
            f"Assigned a {created.credential_type!s} credential to connector {body.connector_id}."
        ),
    )
    return SuccessResponse(
        message="Credential assigned.",
        data=CredentialResponse.model_validate(created),
        meta=_meta(),
    )


@router.get(
    "/{credential_id}",
    response_model=SuccessResponse[CredentialResponse],
    summary="Get a credential",
)
async def get_credential(
    organization_id: UUID, credential_id: UUID, credentials: CredentialSvc
) -> SuccessResponse[CredentialResponse]:
    """One credential -- never returns the resolved secret value itself."""
    found = await credentials.get(organization_id, credential_id)
    return SuccessResponse(
        message="Credential found.", data=CredentialResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "/{credential_id}/rotate",
    response_model=SuccessResponse[CredentialResponse],
    summary="Rotate a credential",
)
async def rotate_credential(
    organization_id: UUID,
    credential_id: UUID,
    body: CredentialRotateRequest,
    credentials: CredentialSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[CredentialResponse]:
    """Replace a self-managed credential's own value."""
    rotated = await credentials.rotate(
        organization_id,
        credential_id,
        raw_value=body.raw_value,
        refresh_value=body.refresh_value,
        expires_at=body.expires_at,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CREDENTIAL_ROTATED,
        entity_type="credential",
        entity_id=credential_id,
        actor_id=str(caller),
        summary=f"Rotated credential {credential_id}.",
    )
    return SuccessResponse(
        message="Credential rotated.", data=CredentialResponse.model_validate(rotated), meta=_meta()
    )


__all__ = ["router"]
