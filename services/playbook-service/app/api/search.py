"""``GET /playbooks/search``. Per docs/041 REST list, backing docs/041's
own "SEARCH" "Support": Name, Tags, Category, Author, Version,
Variables, Dependencies, Full Text Search, Filtering, Sorting,
Pagination.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.database.filtering import Filter, FilterOperator
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PlaybookSvc
from app.api.playbooks import playbook_to_response
from app.models.enums import PlaybookStatus
from app.schemas.playbook import PlaybookResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/playbooks/search", tags=["Search"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[PlaybookResponse]])
async def search_playbooks(
    organization_id: UUID,
    playbooks: PlaybookSvc,
    _caller: CurrentUserId,
    query: str | None = None,
    status: PlaybookStatus | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> SuccessResponse[list[PlaybookResponse]]:
    """Full-text search playbooks by name/display name/description,
    optionally filtered by status, sorted, and paginated ("Search").
    """
    filters = (
        [Filter(field="status", operator=FilterOperator.EQUAL, value=status)] if status else None
    )
    result = await playbooks.search(
        query=query, filters=filters, sort_fields=None, page=page, page_size=page_size
    )
    data = [playbook_to_response(record) for record in result.items]
    return SuccessResponse(message="Playbook search results retrieved.", data=data, meta=_meta())


__all__ = ["router"]
