"""API key management (docs/056 "REST APIs", "API KEY MANAGEMENT")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import ApiKeySvc, AuditSvc, CurrentUserId
from app.models.enums import AuditAction
from app.schemas.gateway import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/apikeys", tags=["API Keys"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[ApiKeyResponse]], summary="List a client's own API keys"
)
async def list_api_keys(
    organization_id: UUID, client_id: UUID, api_keys: ApiKeySvc
) -> SuccessResponse[list[ApiKeyResponse]]:
    """Every key issued to one client."""
    rows = await api_keys.list_for_client(organization_id, client_id)
    return SuccessResponse(
        message="API keys listed.",
        data=[ApiKeyResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[ApiKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new API key",
)
async def create_api_key(
    organization_id: UUID,
    body: ApiKeyCreateRequest,
    api_keys: ApiKeySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ApiKeyCreatedResponse]:
    """Issue a new API key. The raw key is returned exactly once."""
    raw_key, created = await api_keys.create(
        organization_id,
        client_id=body.client_id,
        name=body.name,
        scopes=body.scopes,
        ttl_days=body.ttl_days,
        ip_allowlist=body.ip_allowlist,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.API_KEY_CREATED,
        entity_type="api_key",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Issued API key {created.name!r}.",
    )
    return SuccessResponse(
        message="API key issued.",
        data=ApiKeyCreatedResponse(raw_key=raw_key, api_key=ApiKeyResponse.model_validate(created)),
        meta=_meta(),
    )


@router.put(
    "/{api_key_id}/rotate",
    response_model=SuccessResponse[ApiKeyCreatedResponse],
    summary="Rotate an API key",
)
async def rotate_api_key(
    organization_id: UUID,
    api_key_id: UUID,
    api_keys: ApiKeySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ApiKeyCreatedResponse]:
    """Rotate a key: the old secret stops working, a new one takes its place."""
    raw_key, updated = await api_keys.rotate(organization_id, api_key_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.API_KEY_ROTATED,
        entity_type="api_key",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Rotated API key {updated.name!r}.",
    )
    return SuccessResponse(
        message="API key rotated.",
        data=ApiKeyCreatedResponse(raw_key=raw_key, api_key=ApiKeyResponse.model_validate(updated)),
        meta=_meta(),
    )


@router.delete(
    "/{api_key_id}", response_model=SuccessResponse[ApiKeyResponse], summary="Revoke an API key"
)
async def revoke_api_key(
    organization_id: UUID,
    api_key_id: UUID,
    api_keys: ApiKeySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ApiKeyResponse]:
    """Revoke a key immediately."""
    revoked = await api_keys.revoke(organization_id, api_key_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.API_KEY_REVOKED,
        entity_type="api_key",
        entity_id=revoked.id,
        actor_id=str(caller),
        summary=f"Revoked API key {revoked.name!r}.",
    )
    return SuccessResponse(
        message="API key revoked.", data=ApiKeyResponse.model_validate(revoked), meta=_meta()
    )


__all__ = ["router"]
