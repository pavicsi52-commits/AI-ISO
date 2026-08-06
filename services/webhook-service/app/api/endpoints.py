"""Endpoint management (docs/057 "ENDPOINT MANAGEMENT", "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, EndpointSvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import EndpointCreateRequest, EndpointResponse, EndpointUpdateRequest

router = APIRouter(prefix="/webhooks/endpoints", tags=["Endpoints"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[EndpointResponse]], summary="List endpoints")
async def list_endpoints(
    organization_id: UUID,
    endpoints: EndpointSvc,
    enabled: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[EndpointResponse]]:
    """Endpoints registered in this organization."""
    rows = await endpoints.list_endpoints(organization_id, enabled=enabled)
    return SuccessResponse(
        message="Endpoints listed.",
        data=[EndpointResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{endpoint_id}", response_model=SuccessResponse[EndpointResponse], summary="Get an endpoint"
)
async def get_endpoint(
    organization_id: UUID, endpoint_id: UUID, endpoints: EndpointSvc
) -> SuccessResponse[EndpointResponse]:
    """One endpoint."""
    found = await endpoints.get(organization_id, endpoint_id)
    return SuccessResponse(
        message="Endpoint found.", data=EndpointResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[EndpointResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register an endpoint",
)
async def create_endpoint(
    organization_id: UUID,
    body: EndpointCreateRequest,
    endpoints: EndpointSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[EndpointResponse]:
    """Register a new outgoing-delivery target."""
    created = await endpoints.register(
        organization_id,
        name=body.name,
        url=body.url,
        kind=body.kind,
        auth_method=body.auth_method,
        description=body.description,
        headers=body.headers,
        owner_id=body.owner_id,
        timeout_seconds=body.timeout_seconds,
        max_attempts=body.max_attempts,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.ENDPOINT_REGISTERED,
        entity_type="endpoint",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Registered endpoint {created.name!r}.",
    )
    return SuccessResponse(
        message="Endpoint registered.", data=EndpointResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{endpoint_id}", response_model=SuccessResponse[EndpointResponse], summary="Update an endpoint"
)
async def update_endpoint(
    organization_id: UUID,
    endpoint_id: UUID,
    body: EndpointUpdateRequest,
    endpoints: EndpointSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[EndpointResponse]:
    """Edit an endpoint's editable fields."""
    fields = body.model_dump(exclude_unset=True)
    updated = await endpoints.update(organization_id, endpoint_id, actor_id=str(caller), **fields)
    await audit.record(
        organization_id,
        action=AuditAction.ENDPOINT_UPDATED,
        entity_type="endpoint",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated endpoint {updated.name!r}.",
    )
    return SuccessResponse(
        message="Endpoint updated.", data=EndpointResponse.model_validate(updated), meta=_meta()
    )


@router.delete(
    "/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an endpoint"
)
async def delete_endpoint(
    organization_id: UUID,
    endpoint_id: UUID,
    endpoints: EndpointSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> None:
    """Deregister an endpoint."""
    await endpoints.delete(organization_id, endpoint_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.ENDPOINT_DELETED,
        entity_type="endpoint",
        entity_id=endpoint_id,
        actor_id=str(caller),
        summary=f"Deleted endpoint {endpoint_id}.",
    )


__all__ = ["router"]
