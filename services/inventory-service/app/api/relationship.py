"""``/inventory/relationships``. Per docs/036 REST list."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RelationshipSvc
from app.models.asset_relationship import AssetRelationship
from app.schemas.relationship import AssetRelationshipCreateRequest, AssetRelationshipResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/inventory/relationships", tags=["Relationships"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(relationship: AssetRelationship) -> AssetRelationshipResponse:
    return AssetRelationshipResponse(
        id=relationship.id,
        organization_id=relationship.organization_id,
        source_asset_id=relationship.source_asset_id,
        target_asset_id=relationship.target_asset_id,
        relationship_type=relationship.relationship_type,
        custom_label=relationship.custom_label,
        metadata=relationship.metadata_,
    )


@router.get("", response_model=SuccessResponse[list[AssetRelationshipResponse]])
async def list_relationships(
    asset_id: Annotated[UUID, Query()],
    relationships: RelationshipSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[list[AssetRelationshipResponse]]:
    """Every relationship touching *asset_id*, as either source or
    target ("Relationship Traversal").
    """
    records = await relationships.list_for_asset(asset_id)
    return SuccessResponse(
        message="Relationships retrieved.",
        data=[_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[AssetRelationshipResponse], status_code=201)
async def create_relationship(
    body: AssetRelationshipCreateRequest, relationships: RelationshipSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetRelationshipResponse]:
    """Create a new relationship edge between two assets, mirrored into
    Neo4j.

    Raises:
        ConflictError: If this exact edge already exists.
    """
    relationship = await relationships.create(
        organization_id=body.organization_id,
        source_asset_id=body.source_asset_id,
        target_asset_id=body.target_asset_id,
        relationship_type=body.relationship_type,
        custom_label=body.custom_label,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Relationship created.", data=_to_response(relationship), meta=_meta()
    )


@router.delete("/{relationship_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_relationship(
    relationship_id: UUID, relationships: RelationshipSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete a relationship edge, removing its mirror from Neo4j too.

    Raises:
        NotFoundError: If no such relationship exists.
    """
    await relationships.delete(relationship_id)
    return SuccessResponse(message="Relationship deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
