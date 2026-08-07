"""Marketplace listing administration: create, approve, reject, feature
(docs/059 "MARKETPLACE", extension surface -- ``GET /plugins/marketplace``
itself, the one literal docs/059 endpoint, lives in ``app/api/plugins.py``
alongside the rest of the fifteen literal endpoints).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MarketplaceSvc
from app.schemas.marketplace import (
    PluginMarketplaceListingRequest,
    PluginMarketplaceRejectRequest,
    PluginMarketplaceResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/plugins/marketplace-listings", tags=["Marketplace"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/pending",
    response_model=SuccessResponse[list[PluginMarketplaceResponse]],
    summary="List draft listings awaiting approval",
)
async def list_pending(
    marketplace: MarketplaceSvc, limit: Annotated[int, Query(ge=1, le=1_000)] = 200
) -> SuccessResponse[list[PluginMarketplaceResponse]]:
    """Every draft listing awaiting the marketplace-approval sweep."""
    rows = await marketplace.list_pending_approval(limit=limit)
    return SuccessResponse(
        message="Pending listings found.",
        data=[PluginMarketplaceResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    status_code=201,
    summary="Create a draft marketplace listing",
)
async def create_listing(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginMarketplaceListingRequest,
    marketplace: MarketplaceSvc,
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Create a draft marketplace listing for a plugin."""
    created = await marketplace.create_listing(
        organization_id,
        plugin_id,
        search_keywords=body.search_keywords,
        icon_url=body.icon_url,
        screenshots=body.screenshots,
        pricing_summary=body.pricing_summary,
    )
    return SuccessResponse(
        message="Listing created.",
        data=PluginMarketplaceResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/approve",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    summary="Approve a draft listing",
)
async def approve_listing(
    organization_id: UUID, entry_id: UUID, marketplace: MarketplaceSvc, caller: CurrentUserId
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Approve a draft listing, publishing it to the marketplace."""
    approved = await marketplace.approve(organization_id, entry_id, approved_by=str(caller))
    return SuccessResponse(
        message="Listing approved.",
        data=PluginMarketplaceResponse.model_validate(approved),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/reject",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    summary="Reject a draft listing",
)
async def reject_listing(
    entry_id: UUID, body: PluginMarketplaceRejectRequest, marketplace: MarketplaceSvc
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Reject a draft listing."""
    rejected = await marketplace.reject(entry_id, reason=body.reason)
    return SuccessResponse(
        message="Listing rejected.",
        data=PluginMarketplaceResponse.model_validate(rejected),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/feature",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    summary="Feature a listing",
)
async def feature_listing(
    entry_id: UUID, marketplace: MarketplaceSvc
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Feature a published listing."""
    featured = await marketplace.feature(entry_id)
    return SuccessResponse(
        message="Listing featured.",
        data=PluginMarketplaceResponse.model_validate(featured),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/unfeature",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    summary="Unfeature a listing",
)
async def unfeature_listing(
    entry_id: UUID, marketplace: MarketplaceSvc
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Return a featured listing to plain published status."""
    unfeatured = await marketplace.unfeature(entry_id)
    return SuccessResponse(
        message="Listing unfeatured.",
        data=PluginMarketplaceResponse.model_validate(unfeatured),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/deprecate",
    response_model=SuccessResponse[PluginMarketplaceResponse],
    summary="Deprecate a listing",
)
async def deprecate_listing(
    entry_id: UUID, marketplace: MarketplaceSvc
) -> SuccessResponse[PluginMarketplaceResponse]:
    """Deprecate a listing."""
    deprecated = await marketplace.deprecate(entry_id)
    return SuccessResponse(
        message="Listing deprecated.",
        data=PluginMarketplaceResponse.model_validate(deprecated),
        meta=_meta(),
    )


__all__ = ["router"]
