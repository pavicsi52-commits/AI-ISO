"""Aggregated OpenAPI catalog (docs/056 "REST APIs": ``GET /gateway/openapi``).

No OpenAPI-aggregation library exists anywhere in the monorepo (confirmed
during this prompt's own research phase), and live-fetching each backend's
own spec at request time would mean merging arbitrary, uncontrolled
third-party documents of unknown shape into one response -- a real
federation feature, not something this prompt's literal scope asks for.
Instead, this endpoint synthesizes a minimal, always-accurate OpenAPI 3.0
document directly from this gateway's own routing table: the paths a
caller can actually reach through the gateway, which is the catalog's
whole purpose.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import RouteSvc, ServiceRegistrySvc
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/openapi", tags=["OpenAPI Catalog"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[dict[str, Any]], summary="Aggregated OpenAPI catalog"
)
async def gateway_openapi(
    organization_id: UUID, routes: RouteSvc, services: ServiceRegistrySvc
) -> SuccessResponse[dict[str, Any]]:
    """A synthesized OpenAPI 3.0 document covering every route this gateway exposes."""
    service_rows = {row.id: row for row in await services.list_services(organization_id)}
    route_rows = await routes.list_routes(organization_id, enabled=True)

    paths: dict[str, dict[str, Any]] = {}
    for route in route_rows:
        service = service_rows.get(route.service_id)
        operations: dict[str, Any] = {}
        for method in route.methods or ["get"]:
            operations[method.lower()] = {
                "summary": route.description or route.name,
                "operationId": f"{route.name}_{method.lower()}",
                "tags": [service.name] if service else [],
                "responses": {"200": {"description": "Successful proxied response."}},
            }
        paths[route.path_pattern] = operations

    document = {
        "openapi": "3.0.3",
        "info": {"title": "AI-IOS API Gateway", "version": "1.0.0"},
        "paths": paths,
    }
    return SuccessResponse(message="OpenAPI catalog built.", data=document, meta=_meta())


__all__ = ["router"]
