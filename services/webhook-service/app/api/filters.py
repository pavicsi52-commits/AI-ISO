"""Event-filter management (docs/057 "EVENT FILTERING")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import FilterSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import FilterCreateRequest, FilterResponse

router = APIRouter(prefix="/webhooks/filters", tags=["Filters"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[FilterResponse]], summary="List filters for a subscription"
)
async def list_filters(subscription_id: UUID, filters: FilterSvc) -> SuccessResponse[list[FilterResponse]]:
    """Every enabled filter attached to one subscription."""
    rows = await filters.list_for_subscription(subscription_id)
    return SuccessResponse(
        message="Filters listed.", data=[FilterResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[FilterResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a filter",
)
async def create_filter(
    organization_id: UUID, body: FilterCreateRequest, filters: FilterSvc
) -> SuccessResponse[FilterResponse]:
    """Register a new event-filtering rule set."""
    created = await filters.create(
        organization_id,
        subscription_id=body.subscription_id,
        name=body.name,
        rules=body.rules,
        match_mode=body.match_mode,
    )
    return SuccessResponse(
        message="Filter created.", data=FilterResponse.model_validate(created), meta=_meta()
    )


__all__ = ["router"]
