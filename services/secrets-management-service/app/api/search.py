"""``GET /secrets/search``. Per docs/035 "SECRET SEARCH": Name, Category,
Tags, Owner, Status, Provider, Metadata, Pagination, Sorting, Filtering.

**Scope note**: Tags/Metadata/Provider filtering is not wired into this
endpoint -- docs/035 lists them as searchable dimensions, but doing so
correctly needs a join this endpoint's simple field-filter model
doesn't support without a dedicated subquery builder, the same
documented scope limit ``services/project-service``'s own search
endpoint already established for its own tag/label/metadata dimensions.
Name/Category/Owner/Status (direct columns on ``secret_vault``) and
free-text search across name/description are fully implemented.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.database.filtering import Filter, FilterOperator
from shared_core.database.sorting import parse_sort_expression
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SecretSvc
from app.api.secret import secret_to_summary
from app.models.enums import SecretStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.search import PaginationMetadataResponse, SecretSearchResponse

router = APIRouter(prefix="/secrets/search", tags=["Secrets"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[SecretSearchResponse])
async def search_secrets(
    organization_id: Annotated[UUID, Query()],
    secrets: SecretSvc,
    _caller: CurrentUserId,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[SecretStatus | None, Query()] = None,
    owner_id: Annotated[UUID | None, Query()] = None,
    category_id: Annotated[UUID | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessResponse[SecretSearchResponse]:
    """Search secrets by name/description, filtered and sorted -- never
    returns decrypted values ("Full Text Search", "Pagination",
    "Sorting", "Filtering").
    """
    filters = [
        Filter(field="organization_id", operator=FilterOperator.EQUAL, value=organization_id)
    ]
    if status is not None:
        filters.append(Filter(field="status", operator=FilterOperator.EQUAL, value=status))
    if owner_id is not None:
        filters.append(Filter(field="owner_id", operator=FilterOperator.EQUAL, value=owner_id))
    if category_id is not None:
        filters.append(
            Filter(field="category_id", operator=FilterOperator.EQUAL, value=category_id)
        )

    result = await secrets.search(
        query=q,
        filters=filters,
        sort_fields=parse_sort_expression(sort),
        page=page,
        page_size=page_size,
    )
    data = SecretSearchResponse(
        items=[secret_to_summary(s) for s in result.items],
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
