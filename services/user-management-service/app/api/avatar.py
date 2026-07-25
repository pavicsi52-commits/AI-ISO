"""POST/DELETE /users/avatar."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import AvatarSvc, CurrentUserId, UserSvc
from app.models.avatar import UserAvatar
from app.schemas.avatar import AvatarResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/avatar", tags=["Avatar"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _to_response(avatar: UserAvatar, avatars: AvatarSvc) -> AvatarResponse:
    return AvatarResponse(
        id=avatar.id,
        url=await avatars.presigned_url(avatar),
        thumbnail_url=await avatars.presigned_thumbnail_url(avatar),
        content_type=avatar.content_type,
        size_bytes=avatar.size_bytes,
        width=avatar.width,
        height=avatar.height,
    )


@router.post("", response_model=SuccessResponse[AvatarResponse], status_code=201)
async def upload_avatar(
    avatars: AvatarSvc, users: UserSvc, current_user_id: CurrentUserId, file: UploadFile
) -> SuccessResponse[AvatarResponse]:
    """Upload (or replace) the caller's own avatar ("Upload"/"Replace").

    Raises:
        NotFoundError: If the caller has no matching user record.
    """
    content = await file.read()
    avatar = await avatars.upload(
        current_user_id,
        filename=file.filename or "avatar",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    user = await users.get_by_id(current_user_id)
    if user is None:
        raise NotFoundError(f"User '{current_user_id}' was not found.")
    await users.set_avatar(user, avatar.storage_key)
    data = await _to_response(avatar, avatars)
    return SuccessResponse(message="Avatar uploaded.", data=data, meta=_meta())


@router.delete("", response_model=SuccessResponse[dict[str, bool]])
async def delete_avatar(
    avatars: AvatarSvc, users: UserSvc, current_user_id: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete the caller's own avatar ("Delete").

    Raises:
        NotFoundError: If the caller has no matching user record.
    """
    await avatars.delete(current_user_id)
    user = await users.get_by_id(current_user_id)
    if user is None:
        raise NotFoundError(f"User '{current_user_id}' was not found.")
    await users.set_avatar(user, None)
    return SuccessResponse(message="Avatar deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
