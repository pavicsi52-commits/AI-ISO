"""``GET /inventory/search``. Per docs/036 "SEARCH": Hostname, IP
Address, MAC Address, Serial Number, Vendor, Model, OS, Tags, Labels,
Metadata, Owner, Project, Organization, Full Text Search, Pagination,
Sorting, Filtering.

**Scope note**: Tags/Labels/Metadata filtering is not wired into this
endpoint -- docs/036 lists them as searchable dimensions, but doing so
correctly needs a join against ``asset_tags``/``asset_labels``/
``asset_metadata`` this endpoint's simple field-filter model doesn't
support without a dedicated subquery builder, the same documented
follow-up ``services/project-service``'s own ``/projects/search``
already established for its identical gap. Hostname/IP/MAC/Serial/
Vendor/Model/OS/Owner/Project/Organization (direct columns on
``inventory_assets`` itself) and free-text search across those same
columns are fully implemented.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.database.filtering import Filter, FilterOperator
from shared_core.database.sorting import parse_sort_expression
from shared_core.logging.context import get_log_context

from app.api.asset import asset_to_response
from app.api.deps import AssetSvc, CurrentUserId, TagSvc
from app.models.enums import AssetStatus, AssetType
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.search import AssetSearchResponse, PaginationMetadataResponse

router = APIRouter(prefix="/inventory/search", tags=["Search"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[AssetSearchResponse])
async def search_assets(
    organization_id: Annotated[UUID, Query()],
    assets: AssetSvc,
    tags: TagSvc,
    _caller: CurrentUserId,
    q: Annotated[str | None, Query()] = None,
    asset_type: Annotated[AssetType | None, Query()] = None,
    status: Annotated[AssetStatus | None, Query()] = None,
    owner_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessResponse[AssetSearchResponse]:
    """Search assets by hostname/IP/MAC/serial/vendor/model/OS, filtered
    and sorted ("Full Text Search", "Pagination", "Sorting", "Filtering").
    """
    filters = [
        Filter(field="organization_id", operator=FilterOperator.EQUAL, value=organization_id)
    ]
    if asset_type is not None:
        filters.append(Filter(field="asset_type", operator=FilterOperator.EQUAL, value=asset_type))
    if status is not None:
        filters.append(Filter(field="status", operator=FilterOperator.EQUAL, value=status))
    if owner_id is not None:
        filters.append(Filter(field="owner_id", operator=FilterOperator.EQUAL, value=owner_id))
    if project_id is not None:
        filters.append(Filter(field="project_id", operator=FilterOperator.EQUAL, value=project_id))

    result = await assets.search(
        query=q,
        filters=filters,
        sort_fields=parse_sort_expression(sort),
        page=page,
        page_size=page_size,
    )
    data = AssetSearchResponse(
        items=[await asset_to_response(asset, tags) for asset in result.items],
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
