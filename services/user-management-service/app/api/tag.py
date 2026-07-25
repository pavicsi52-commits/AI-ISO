"""GET/POST/DELETE /users/tags{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TagSvc
from app.models.tag import UserTag
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.tag import TagCreateRequest, TagResponse

router = APIRouter(prefix="/users/tags", tags=["Tags"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(tag: UserTag) -> TagResponse:
    return TagResponse(id=tag.id, label=tag.label, category=tag.category)


@router.post("", response_model=SuccessResponse[TagResponse], status_code=201)
async def assign_tag(
    body: TagCreateRequest, tags: TagSvc, current_user_id: CurrentUserId
) -> SuccessResponse[TagResponse]:
    """Assign a new tag to the caller ("Custom Tags")."""
    tag = await tags.assign(current_user_id, label=body.label, category=body.category)
    return SuccessResponse(message="Tag assigned.", data=_to_response(tag), meta=_meta())


@router.get("", response_model=SuccessResponse[list[TagResponse]])
async def list_tags(
    tags: TagSvc, current_user_id: CurrentUserId
) -> SuccessResponse[list[TagResponse]]:
    """List the caller's own tags."""
    records = await tags.list_for_user(current_user_id)
    return SuccessResponse(
        message="Tags retrieved.", data=[_to_response(t) for t in records], meta=_meta()
    )


@router.delete("/{tag_id}", response_model=SuccessResponse[dict[str, bool]])
async def remove_tag(
    tag_id: UUID, tags: TagSvc, current_user_id: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Remove one of the caller's own tags."""
    await tags.remove(current_user_id, tag_id)
    return SuccessResponse(message="Tag removed.", data={"success": True}, meta=_meta())


__all__ = ["router"]
