"""Payload/header transformation management (docs/057 "PAYLOAD TRANSFORMATION")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import EndpointSvc, TransformationSvc
from app.models.enums import transformation_kind_of
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import TransformationCreateRequest, TransformationResponse

router = APIRouter(prefix="/webhooks/transformations", tags=["Transformations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[list[TransformationResponse]],
    summary="List transformation rules for an endpoint",
)
async def list_transformations(
    organization_id: UUID, endpoint_id: UUID, endpoints: EndpointSvc, transformations: TransformationSvc
) -> SuccessResponse[list[TransformationResponse]]:
    """Every enabled transformation rule attached to one endpoint in this organization, in priority order.

    Confirms *endpoint_id* actually belongs to *organization_id* first
    (docs/057 "SECURITY": "Organization isolation") -- a
    ``WebhookTransformation`` row is not directly reachable by
    organization otherwise, since a rule is looked up by its parent
    endpoint, not listed per organization.
    """
    await endpoints.get(organization_id, endpoint_id)
    rows = await transformations.list_for_endpoint(endpoint_id)
    return SuccessResponse(
        message="Transformation rules listed.",
        data=[TransformationResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[TransformationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a transformation rule",
)
async def create_transformation(
    organization_id: UUID,
    body: TransformationCreateRequest,
    endpoints: EndpointSvc,
    transformations: TransformationSvc,
) -> SuccessResponse[TransformationResponse]:
    """Register a new transformation rule.

    Confirms ``body.endpoint_id`` actually belongs to *organization_id*
    first -- otherwise a caller could attach a transformation rule to
    (and thereby alter outbound deliveries for) another organization's
    own endpoint.
    """
    await endpoints.get(organization_id, body.endpoint_id)
    created = await transformations.create(
        organization_id,
        endpoint_id=body.endpoint_id,
        name=body.name,
        kind=transformation_kind_of(body.kind),
        config=body.config,
        priority=body.priority,
    )
    return SuccessResponse(
        message="Transformation rule created.",
        data=TransformationResponse.model_validate(created),
        meta=_meta(),
    )


__all__ = ["router"]
