"""``/api-keys``. Per docs/035 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ApiKeySvc, CurrentUserId
from app.models.api_key import ApiKeyEntry
from app.schemas.api_key import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(api_key: ApiKeyEntry) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        organization_id=api_key.organization_id,
        project_id=api_key.project_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        secret_id=api_key.secret_id,
        scopes=api_key.scopes,
        status=api_key.status,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[ApiKeyResponse]])
async def list_api_keys(
    organization_id: UUID, api_keys: ApiKeySvc, _caller: CurrentUserId
) -> SuccessResponse[list[ApiKeyResponse]]:
    """List every managed API key belonging to *organization_id* -- never values."""
    records = await api_keys.list_for_org(organization_id)
    return SuccessResponse(
        message="API keys retrieved.", data=[_to_response(k) for k in records], meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ApiKeyCreateResponse], status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest, api_keys: ApiKeySvc, _caller: CurrentUserId
) -> SuccessResponse[ApiKeyCreateResponse]:
    """Generate a fresh API key value, or import an existing one ("Generation")."""
    api_key, value = await api_keys.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        owner_id=body.owner_id,
        scopes=body.scopes,
        expires_at=body.expires_at,
        value=body.value,
    )
    data = ApiKeyCreateResponse(**_to_response(api_key).model_dump(), value=value)
    return SuccessResponse(message="API key created.", data=data, meta=_meta())


@router.delete("/{api_key_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_api_key(
    api_key_id: UUID, api_keys: ApiKeySvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete an API key ("Revocation")."""
    await api_keys.delete(api_key_id)
    return SuccessResponse(message="API key deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
