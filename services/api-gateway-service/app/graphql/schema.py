"""GraphQL schema: gateway-level queries.

Exposes services/routes/statistics as GraphQL, reading through this same
service's own :class:`~app.services.service.ServiceRegistryService`,
:class:`~app.services.route.RouteService`, and
:class:`~app.services.reporting.StatisticsService` -- no separate data
path, so a GraphQL query and its REST equivalent can never disagree.

**Single-schema today, not federation.** No backend service registered
with this gateway currently exposes its own GraphQL schema, so there is
nothing yet to federate; this schema covers the gateway's own management
data only. Extending it into an Apollo-Federation-style aggregator is a
real, separate feature for whenever a backend speaks GraphQL -- stated
here as a scope boundary rather than left silently unfulfilled.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import strawberry


@strawberry.type
class GraphQLService:
    """A registered backend service."""

    id: UUID
    name: str
    description: str | None
    load_balancing_strategy: str
    health_check_path: str
    enabled: bool
    instance_count: int


@strawberry.type
class GraphQLRoute:
    """A configured routing rule."""

    id: UUID
    service_id: UUID
    name: str
    match_kind: str
    path_pattern: str
    methods: list[str]
    priority: int
    enabled: bool


@strawberry.type
class GraphQLStatisticsWindow:
    """The latest rolled-up traffic window."""

    error_rate: float | None
    success_rate: float | None
    average_latency_ms: float | None
    p95_latency_ms: float | None
    computed_through: str | None


@strawberry.type
class Query:
    """Gateway-level read queries."""

    @strawberry.field
    async def services(
        self, info: strawberry.Info[Any, Any], organization_id: UUID, enabled: bool | None = None
    ) -> list[GraphQLService]:
        """Backend services registered in this organization."""
        registry = info.context["services"]
        rows = await registry.list_services(organization_id, enabled=enabled)
        return [
            GraphQLService(
                id=row.id,
                name=row.name,
                description=row.description,
                load_balancing_strategy=str(row.load_balancing_strategy),
                health_check_path=row.health_check_path,
                enabled=row.enabled,
                instance_count=len(row.instances),
            )
            for row in rows
        ]

    @strawberry.field
    async def routes(
        self, info: strawberry.Info[Any, Any], organization_id: UUID, service_id: UUID | None = None
    ) -> list[GraphQLRoute]:
        """Routes configured in this organization."""
        route_service = info.context["routes"]
        rows = await route_service.list_routes(organization_id, service_id=service_id)
        return [
            GraphQLRoute(
                id=row.id,
                service_id=row.service_id,
                name=row.name,
                match_kind=str(row.match_kind),
                path_pattern=row.path_pattern,
                methods=list(row.methods),
                priority=row.priority,
                enabled=row.enabled,
            )
            for row in rows
        ]

    @strawberry.field
    async def statistics(
        self, info: strawberry.Info[Any, Any], organization_id: UUID
    ) -> GraphQLStatisticsWindow:
        """The latest traffic statistics window for this organization."""
        statistics = info.context["statistics"]
        dashboard = await statistics.dashboard(organization_id)
        latest = dashboard["latest_window"]
        return GraphQLStatisticsWindow(
            error_rate=latest["error_rate"],
            success_rate=latest["success_rate"],
            average_latency_ms=latest["average_latency_ms"],
            p95_latency_ms=latest["p95_latency_ms"],
            computed_through=latest["computed_through"],
        )


schema = strawberry.Schema(query=Query)

__all__ = ["Query", "schema"]
