"""The connector marketplace (docs/058 "MARKETPLACE", "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, MarketplaceSvc
from app.models.enums import AuditAction, ConnectorCategory
from app.schemas.hub import (
    MarketplaceEntryResponse,
    MarketplacePublishRequest,
    MarketplaceRateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations/marketplace", tags=["Marketplace"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[MarketplaceEntryResponse]], summary="List the catalog"
)
async def list_marketplace(
    organization_id: UUID,
    marketplace: MarketplaceSvc,
    category: Annotated[ConnectorCategory | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[MarketplaceEntryResponse]]:
    """Catalog entries visible in this organization -- seeds the built-in catalog on first call."""
    if not await marketplace.list_for_org(organization_id, limit=1):
        await marketplace.seed_builtin_catalog(organization_id)
    rows = await marketplace.list_for_org(
        organization_id, category=category, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Marketplace listed.",
        data=[MarketplaceEntryResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{entry_id}",
    response_model=SuccessResponse[MarketplaceEntryResponse],
    summary="Get a catalog entry",
)
async def get_marketplace_entry(
    organization_id: UUID, entry_id: UUID, marketplace: MarketplaceSvc
) -> SuccessResponse[MarketplaceEntryResponse]:
    """One catalog entry."""
    found = await marketplace.get(organization_id, entry_id)
    return SuccessResponse(
        message="Marketplace entry found.",
        data=MarketplaceEntryResponse.model_validate(found),
        meta=_meta(),
    )


@router.post(
    "/publish",
    response_model=SuccessResponse[MarketplaceEntryResponse],
    status_code=201,
    summary="Publish a connector to the catalog",
)
async def publish_marketplace_entry(
    organization_id: UUID,
    body: MarketplacePublishRequest,
    marketplace: MarketplaceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[MarketplaceEntryResponse]:
    """Publish a new (non-built-in) connector to this organization's own catalog."""
    created = await marketplace.publish(
        organization_id,
        slug=body.slug,
        name=body.name,
        category=body.category,
        description=body.description,
        publisher=body.publisher,
        version_number=body.version_number,
        supported_auth_methods=body.supported_auth_methods,
        dependencies=body.dependencies,
        published_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.MARKETPLACE_PUBLISHED,
        entity_type="marketplace_entry",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Published marketplace entry {created.slug!r}.",
    )
    return SuccessResponse(
        message="Marketplace entry published.",
        data=MarketplaceEntryResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/{entry_id}/rate",
    response_model=SuccessResponse[MarketplaceEntryResponse],
    summary="Rate a catalog entry",
)
async def rate_marketplace_entry(
    organization_id: UUID, entry_id: UUID, body: MarketplaceRateRequest, marketplace: MarketplaceSvc
) -> SuccessResponse[MarketplaceEntryResponse]:
    """Record a ``1``-``5`` rating for a catalog entry."""
    rated = await marketplace.rate(organization_id, entry_id, rating=body.rating)
    return SuccessResponse(
        message="Rating recorded.",
        data=MarketplaceEntryResponse.model_validate(rated),
        meta=_meta(),
    )


__all__ = ["router"]
