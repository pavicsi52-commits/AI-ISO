"""GET/PUT/DELETE /users/metadata{,/{key}}."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MetadataSvc
from app.schemas.metadata import MetadataEntryResponse, MetadataSetRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/metadata", tags=["Metadata"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[MetadataEntryResponse]])
async def list_metadata(
    metadata: MetadataSvc, current_user_id: CurrentUserId
) -> SuccessResponse[list[MetadataEntryResponse]]:
    """List the caller's own custom metadata entries."""
    records = await metadata.list_for_user(current_user_id)
    data = [MetadataEntryResponse(key=entry.key, value=entry.value) for entry in records]
    return SuccessResponse(message="Metadata retrieved.", data=data, meta=_meta())


@router.put("/{key}", response_model=SuccessResponse[MetadataEntryResponse])
async def set_metadata(
    key: str, body: MetadataSetRequest, metadata: MetadataSvc, current_user_id: CurrentUserId
) -> SuccessResponse[MetadataEntryResponse]:
    """Set the caller's own metadata entry for *key* ("Metadata Updates")."""
    entry = await metadata.set(current_user_id, key, body.value)
    return SuccessResponse(
        message="Metadata updated.",
        data=MetadataEntryResponse(key=entry.key, value=entry.value),
        meta=_meta(),
    )


@router.delete("/{key}", response_model=SuccessResponse[dict[str, bool]])
async def delete_metadata(
    key: str, metadata: MetadataSvc, current_user_id: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Remove the caller's own metadata entry for *key*."""
    await metadata.remove(current_user_id, key)
    return SuccessResponse(message="Metadata removed.", data={"success": True}, meta=_meta())


__all__ = ["router"]
