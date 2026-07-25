"""GET /users/activity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import ActivitySvc, CurrentUserId
from app.schemas.activity import ActivityEntryResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/activity", tags=["Activity"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ActivityEntryResponse]])
async def list_activity(
    activity: ActivitySvc,
    current_user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SuccessResponse[list[ActivityEntryResponse]]:
    """List the caller's own recent activity ("Last Active")."""
    entries = await activity.list_recent(current_user_id, limit=limit)
    data = [
        ActivityEntryResponse(
            id=entry.id,
            activity_type=entry.activity_type,
            description=entry.description,
            detail=entry.detail,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
    return SuccessResponse(message="Activity retrieved.", data=data, meta=_meta())


__all__ = ["router"]
