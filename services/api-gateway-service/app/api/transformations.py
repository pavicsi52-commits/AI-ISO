"""Request/response transformation rule management (docs/056 "REQUEST/RESPONSE TRANSFORMATION")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import TransformationSvc
from app.models.enums import transformation_direction_of, transformation_kind_of
from app.schemas.gateway import TransformationRuleRequest, TransformationRuleResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/transformations", tags=["Transformations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[TransformationRuleResponse]], summary="List transformation rules"
)
async def list_transformations(
    organization_id: UUID,
    transformations: TransformationSvc,
    route_id: Annotated[UUID | None, Query()] = None,
) -> SuccessResponse[list[TransformationRuleResponse]]:
    """Every enabled rule applying to *route_id* (or every global rule if omitted)."""
    rows = await transformations.list_for_route(organization_id, route_id)
    return SuccessResponse(
        message="Transformation rules listed.",
        data=[TransformationRuleResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[TransformationRuleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a transformation rule",
)
async def create_transformation(
    organization_id: UUID, body: TransformationRuleRequest, transformations: TransformationSvc
) -> SuccessResponse[TransformationRuleResponse]:
    """Register a new request/response transformation rule."""
    created = await transformations.create(
        organization_id,
        name=body.name,
        kind=transformation_kind_of(body.kind),
        direction=transformation_direction_of(body.direction),
        config=body.config,
        route_id=body.route_id,
        priority=body.priority,
    )
    return SuccessResponse(
        message="Transformation rule created.",
        data=TransformationRuleResponse.model_validate(created),
        meta=_meta(),
    )


__all__ = ["router"]
