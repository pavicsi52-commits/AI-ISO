"""``GET /projects/search``. Per docs/034 "SEARCH": Project Name, Project
Code, Tags, Labels, Owner, Status, Organization, Metadata, Full Text
Search, Pagination, Sorting, Filtering.

**Scope note**: Tags/Labels/Metadata filtering is not wired into this
endpoint -- docs/034 lists them as searchable dimensions, but doing so
correctly needs a join against ``project_tags``/``project_labels``/
``project_metadata`` this endpoint's simple field-filter model doesn't
support without a dedicated subquery builder. Name/Code/Owner/Status/
Organization (direct columns on ``projects`` itself) and free-text
search across name/code/description/category are fully implemented;
tag/label/metadata search is a documented follow-up, not silently
dropped.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.database.filtering import Filter, FilterOperator
from shared_core.database.sorting import parse_sort_expression
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MemberSvc, ProjSvc
from app.api.project import project_to_response
from app.models.enums import ProjectStatus, ProjectVisibility
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.search import PaginationMetadataResponse, ProjectSearchResponse

router = APIRouter(prefix="/projects/search", tags=["Projects"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[ProjectSearchResponse])
async def search_projects(
    organization_id: Annotated[UUID, Query()],
    projects: ProjSvc,
    members: MemberSvc,
    caller: CurrentUserId,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[ProjectStatus | None, Query()] = None,
    owner_id: Annotated[UUID | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessResponse[ProjectSearchResponse]:
    """Search projects by name/code/description, filtered and sorted
    ("Full Text Search", "Pagination", "Sorting", "Filtering").
    """
    filters = [
        Filter(field="organization_id", operator=FilterOperator.EQUAL, value=organization_id)
    ]
    if status is not None:
        filters.append(Filter(field="status", operator=FilterOperator.EQUAL, value=status))
    if owner_id is not None:
        filters.append(Filter(field="owner_id", operator=FilterOperator.EQUAL, value=owner_id))

    result = await projects.search(
        query=q,
        filters=filters,
        sort_fields=parse_sort_expression(sort),
        page=page,
        page_size=page_size,
    )
    member_project_ids = await members.project_ids_for_user(caller)
    visible = [
        p
        for p in result.items
        if p.visibility != ProjectVisibility.PRIVATE or p.id in member_project_ids
    ]

    data = ProjectSearchResponse(
        items=[project_to_response(p) for p in visible],
        pagination=PaginationMetadataResponse(
            total=result.metadata.total,
            page=result.metadata.page,
            page_size=result.metadata.page_size,
            total_pages=result.metadata.total_pages,
            has_next=result.metadata.has_next,
            has_previous=result.metadata.has_previous,
        ),
    )
    return SuccessResponse(message="Search results retrieved.", data=data, meta=_meta())


__all__ = ["router"]
