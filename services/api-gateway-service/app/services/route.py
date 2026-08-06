"""Route configuration and resolution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import RouteMatchKind
from app.models.route import ApiRoute
from app.repositories.route import ApiRouteRepository
from app.routing import engine as routing_engine

_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "path_pattern",
        "host_pattern",
        "methods",
        "header_match",
        "weight",
        "priority",
        "strip_prefix",
        "rewrite_path",
        "requires_auth",
        "allowed_auth_methods",
        "required_scopes",
        "required_permission",
        "description",
        "enabled",
    }
)


class RouteService:
    """Routes: configuration, editing, and resolution."""

    def __init__(self, routes: ApiRouteRepository) -> None:
        self._routes = routes

    async def create(
        self,
        organization_id: UUID,
        *,
        service_id: UUID,
        name: str,
        path_pattern: str,
        match_kind: RouteMatchKind = RouteMatchKind.PATH,
        version_id: UUID | None = None,
        host_pattern: str | None = None,
        methods: list[str] | None = None,
        header_match: dict[str, str] | None = None,
        weight: int = 100,
        priority: int = 100,
        strip_prefix: bool = False,
        rewrite_path: str | None = None,
        requires_auth: bool = True,
        allowed_auth_methods: list[str] | None = None,
        required_scopes: list[str] | None = None,
        required_permission: str | None = None,
        is_fallback: bool = False,
        description: str | None = None,
        actor_id: str | None = None,
    ) -> ApiRoute:
        """Register a new routing rule."""
        return await self._routes.create(
            ApiRoute(
                organization_id=organization_id,
                service_id=service_id,
                version_id=version_id,
                name=name,
                match_kind=match_kind,
                path_pattern=path_pattern,
                host_pattern=host_pattern,
                methods=[m.lower() for m in (methods or [])],
                header_match=dict(header_match or {}),
                weight=weight,
                priority=priority,
                strip_prefix=strip_prefix,
                rewrite_path=rewrite_path,
                requires_auth=requires_auth,
                allowed_auth_methods=list(allowed_auth_methods or []),
                required_scopes=list(required_scopes or []),
                required_permission=required_permission,
                is_fallback=is_fallback,
                description=description,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, route_id: UUID) -> ApiRoute:
        """One route.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._routes.require_in_org(organization_id, route_id)

    async def list_routes(
        self, organization_id: UUID, *, service_id: UUID | None = None, enabled: bool | None = None
    ) -> list[ApiRoute]:
        """Routes in this organization, ordered by priority."""
        return await self._routes.list_for_org(
            organization_id, service_id=service_id, enabled=enabled
        )

    async def update(
        self, organization_id: UUID, route_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> ApiRoute:
        """Edit a route's editable fields."""
        stored = await self._routes.require_in_org(organization_id, route_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._routes.update(stored)

    async def delete(
        self, organization_id: UUID, route_id: UUID, *, actor_id: str | None = None
    ) -> None:
        """Remove a routing rule."""
        stored = await self._routes.require_in_org(organization_id, route_id)
        await self._routes.delete(stored.id, deleted_by=UUID(actor_id) if actor_id else None)

    async def resolve(
        self,
        organization_id: UUID,
        *,
        method: str,
        path: str,
        host: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> ApiRoute | None:
        """Resolve which route (if any) should handle this request."""
        routes = await self._routes.list_for_org(organization_id, enabled=True)
        candidates = [
            routing_engine.RouteCandidate(
                id=str(route.id),
                service_id=str(route.service_id),
                match_kind=RouteMatchKind(route.match_kind),
                path_pattern=route.path_pattern,
                host_pattern=route.host_pattern,
                methods=tuple(route.methods),
                header_match=route.header_match,
                weight=route.weight,
                priority=route.priority,
                strip_prefix=route.strip_prefix,
                rewrite_path=route.rewrite_path,
                is_fallback=route.is_fallback,
                enabled=route.enabled,
            )
            for route in routes
        ]
        chosen = routing_engine.select_route(
            candidates, method=method, path=path, host=host, headers=headers
        )
        if chosen is None:
            return None
        return next(route for route in routes if str(route.id) == chosen.id)


__all__ = ["RouteService"]
