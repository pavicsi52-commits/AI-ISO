"""POST/GET/DELETE /auth/apikeys{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ApiKeySvc, CurrentUser
from app.schemas.apikey import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeySummary
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth/apikeys", tags=["API Keys"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post("", response_model=SuccessResponse[ApiKeyCreatedResponse], status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest, user: CurrentUser, api_keys: ApiKeySvc
) -> SuccessResponse[ApiKeyCreatedResponse]:
    """Create a new API key. The raw key is returned once and never retrievable again."""
    record, raw_key = await api_keys.create(
        user.id,
        name=body.name,
        scopes=body.scopes,
        expires_in_days=body.expires_in_days,
    )
    data = ApiKeyCreatedResponse(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        raw_key=raw_key,
        scopes=body.scopes,
        expires_at=record.expires_at,
    )
    return SuccessResponse(message="API key created.", data=data, meta=_meta())


@router.get("", response_model=SuccessResponse[list[ApiKeySummary]])
async def list_api_keys(
    user: CurrentUser, api_keys: ApiKeySvc
) -> SuccessResponse[list[ApiKeySummary]]:
    """List every API key belonging to the authenticated caller."""
    records = await api_keys.list_for_user(user.id)
    data = [
        ApiKeySummary(
            id=record.id,
            name=record.name,
            key_prefix=record.key_prefix,
            scopes=record.scopes.split(",") if record.scopes else [],
            expires_at=record.expires_at,
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
        )
        for record in records
    ]
    return SuccessResponse(message="API keys retrieved.", data=data, meta=_meta())


@router.delete("/{api_key_id}", response_model=SuccessResponse[dict[str, bool]])
async def revoke_api_key(
    api_key_id: UUID, user: CurrentUser, api_keys: ApiKeySvc
) -> SuccessResponse[dict[str, bool]]:
    """Revoke one of the caller's own API keys.

    Raises:
        NotFoundError: If no such key belongs to the caller.
    """
    await api_keys.revoke(user.id, api_key_id)
    return SuccessResponse(message="API key revoked.", data={"success": True}, meta=_meta())


__all__ = ["router"]
