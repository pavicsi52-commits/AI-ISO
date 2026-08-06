"""Routing table management (docs/056 "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, RouteSvc
from app.models.enums import AuditAction
from app.schemas.gateway import RouteCreateRequest, RouteResponse, RouteUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/routes", tags=["Routes"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[RouteResponse]], summary="List routes")
async def list_routes(
    organization_id: UUID,
    routes: RouteSvc,
    service_id: Annotated[UUID | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[RouteResponse]]:
    """Routes in this organization, ordered by priority."""
    rows = await routes.list_routes(organization_id, service_id=service_id, enabled=enabled)
    return SuccessResponse(
        message="Routes listed.", data=[RouteResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.get("/{route_id}", response_model=SuccessResponse[RouteResponse], summary="Get a route")
async def get_route(
    organization_id: UUID, route_id: UUID, routes: RouteSvc
) -> SuccessResponse[RouteResponse]:
    """One route."""
    found = await routes.get(organization_id, route_id)
    return SuccessResponse(
        message="Route found.", data=RouteResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[RouteResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a route",
)
async def create_route(
    organization_id: UUID,
    body: RouteCreateRequest,
    routes: RouteSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RouteResponse]:
    """Register a new routing rule."""
    created = await routes.create(
        organization_id,
        service_id=body.service_id,
        name=body.name,
        match_kind=body.match_kind,
        version_id=body.version_id,
        path_pattern=body.path_pattern,
        host_pattern=body.host_pattern,
        methods=body.methods,
        header_match=body.header_match,
        weight=body.weight,
        priority=body.priority,
        strip_prefix=body.strip_prefix,
        rewrite_path=body.rewrite_path,
        requires_auth=body.requires_auth,
        allowed_auth_methods=body.allowed_auth_methods,
        required_scopes=body.required_scopes,
        required_permission=body.required_permission,
        is_fallback=body.is_fallback,
        description=body.description,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.ROUTE_CREATED,
        entity_type="route",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Created route {created.name!r}.",
    )
    return SuccessResponse(
        message="Route created.", data=RouteResponse.model_validate(created), meta=_meta()
    )


@router.put("/{route_id}", response_model=SuccessResponse[RouteResponse], summary="Update a route")
async def update_route(
    organization_id: UUID,
    route_id: UUID,
    body: RouteUpdateRequest,
    routes: RouteSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RouteResponse]:
    """Edit a route's editable fields."""
    fields = body.model_dump(exclude_unset=True)
    updated = await routes.update(organization_id, route_id, actor_id=str(caller), **fields)
    await audit.record(
        organization_id,
        action=AuditAction.ROUTE_UPDATED,
        entity_type="route",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated route {updated.name!r}.",
    )
    return SuccessResponse(
        message="Route updated.", data=RouteResponse.model_validate(updated), meta=_meta()
    )


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a route")
async def delete_route(
    organization_id: UUID, route_id: UUID, routes: RouteSvc, audit: AuditSvc, caller: CurrentUserId
) -> None:
    """Remove a routing rule."""
    await routes.delete(organization_id, route_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.ROUTE_DELETED,
        entity_type="route",
        entity_id=route_id,
        actor_id=str(caller),
        summary=f"Deleted route {route_id}.",
    )


__all__ = ["router"]
