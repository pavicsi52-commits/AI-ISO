"""RouteService and ApiRouteRepository: configuration, editing, and resolution.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``resolve()`` is the integration point between this service and the pure
``app.routing.engine`` module (tested exhaustively elsewhere in isolation):
these tests prove the service correctly assembles ``RouteCandidate``s from
real persisted rows and returns the actual matching ``ApiRoute`` row -- not
the matching algorithm's own behaviour in depth.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import RouteMatchKind
from app.repositories.route import ApiRouteRepository
from app.services.route import RouteService
from app.services.version import VersionService


class TestCreate:
    async def test_creates_with_defaults(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await route_service.create(
            organization_id, service_id=service.id, name="orders-route", path_pattern="/orders/*"
        )
        assert created.name == "orders-route"
        assert created.match_kind == RouteMatchKind.PATH
        assert created.methods == []
        assert created.header_match == {}
        assert created.weight == 100
        assert created.priority == 100
        assert created.strip_prefix is False
        assert created.rewrite_path is None
        assert created.requires_auth is True
        assert created.allowed_auth_methods == []
        assert created.required_scopes == []
        assert created.required_permission is None
        assert created.is_fallback is False
        assert created.enabled is True
        assert created.version_id is None

    async def test_lowercases_methods(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await route_service.create(
            organization_id,
            service_id=service.id,
            name="orders-route",
            path_pattern="/orders",
            methods=["GET", "Post"],
        )
        assert created.methods == ["get", "post"]

    async def test_creates_with_custom_fields(
        self,
        route_service: RouteService,
        version_service: VersionService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        service = await make_service()
        version = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        created = await route_service.create(
            organization_id,
            service_id=service.id,
            name="orders-route",
            path_pattern="/orders/*",
            match_kind=RouteMatchKind.WEIGHTED,
            version_id=version.id,
            host_pattern="*.example.com",
            header_match={"x-api-version": "2"},
            weight=30,
            priority=5,
            strip_prefix=True,
            rewrite_path="/v2/orders",
            requires_auth=False,
            allowed_auth_methods=["jwt"],
            required_scopes=["orders:read"],
            required_permission="orders.view",
            is_fallback=True,
            description="Custom route",
        )
        assert created.match_kind == RouteMatchKind.WEIGHTED
        assert created.version_id == version.id
        assert created.host_pattern == "*.example.com"
        assert created.header_match == {"x-api-version": "2"}
        assert created.weight == 30
        assert created.priority == 5
        assert created.strip_prefix is True
        assert created.rewrite_path == "/v2/orders"
        assert created.requires_auth is False
        assert created.allowed_auth_methods == ["jwt"]
        assert created.required_scopes == ["orders:read"]
        assert created.required_permission == "orders.view"
        assert created.is_fallback is True
        assert created.description == "Custom route"

    async def test_sets_created_by_from_actor_id(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        actor_id = uuid.uuid4()
        created = await route_service.create(
            organization_id,
            service_id=service.id,
            name="orders-route",
            path_pattern="/orders",
            actor_id=str(actor_id),
        )
        assert created.created_by == actor_id


class TestGet:
    async def test_returns_the_matching_route(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        found = await route_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, route_service: RouteService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await route_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, route_service: RouteService, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        with pytest.raises(NotFoundError):
            await route_service.get(uuid.uuid4(), created.id)


class TestListRoutes:
    async def test_orders_by_priority(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        low = await make_route(service.id, name="low", priority=50)
        high = await make_route(service.id, name="high", priority=5)
        routes = await route_service.list_routes(organization_id)
        ids_in_order = [r.id for r in routes]
        assert ids_in_order.index(high.id) < ids_in_order.index(low.id)

    async def test_filters_by_service_id(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        route_a = await make_route(service_a.id, name="route-a")
        await make_route(service_b.id, name="route-b")

        found = await route_service.list_routes(organization_id, service_id=service_a.id)
        assert [r.id for r in found] == [route_a.id]

    async def test_filters_by_enabled(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        enabled_route = await make_route(service.id, name="enabled-route")
        disabled_route = await make_route(service.id, name="disabled-route")
        await route_service.update(organization_id, disabled_route.id, enabled=False)

        only_enabled = await route_service.list_routes(organization_id, enabled=True)
        ids = {r.id for r in only_enabled}
        assert enabled_route.id in ids
        assert disabled_route.id not in ids

    async def test_tenant_isolation(
        self, route_service: RouteService, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id)
        found = await route_service.list_routes(uuid.uuid4())
        assert found == []


class TestUpdate:
    async def test_updates_editable_fields(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        updated = await route_service.update(
            organization_id,
            created.id,
            name="renamed",
            path_pattern="/new/*",
            host_pattern="new.example.com",
            methods=["put"],
            header_match={"x-new": "1"},
            weight=10,
            priority=1,
            strip_prefix=True,
            rewrite_path="/rewritten",
            requires_auth=False,
            allowed_auth_methods=["api_key"],
            required_scopes=["scope:x"],
            required_permission="perm.x",
            description="new description",
            enabled=False,
        )
        assert updated.name == "renamed"
        assert updated.path_pattern == "/new/*"
        assert updated.host_pattern == "new.example.com"
        assert updated.methods == ["put"]
        assert updated.header_match == {"x-new": "1"}
        assert updated.weight == 10
        assert updated.priority == 1
        assert updated.strip_prefix is True
        assert updated.rewrite_path == "/rewritten"
        assert updated.requires_auth is False
        assert updated.allowed_auth_methods == ["api_key"]
        assert updated.required_scopes == ["scope:x"]
        assert updated.required_permission == "perm.x"
        assert updated.description == "new description"
        assert updated.enabled is False

    async def test_ignores_a_non_editable_field(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        created = await make_route(service_a.id)
        updated = await route_service.update(organization_id, created.id, service_id=service_b.id)
        assert updated.service_id == service_a.id

    async def test_ignores_none_values(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id, description="Keep me")
        updated = await route_service.update(
            organization_id, created.id, description=None, weight=42
        )
        assert updated.description == "Keep me"
        assert updated.weight == 42

    async def test_sets_updated_by_from_actor_id(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        actor_id = uuid.uuid4()
        updated = await route_service.update(
            organization_id, created.id, actor_id=str(actor_id), enabled=False
        )
        assert updated.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, route_service: RouteService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await route_service.update(organization_id, uuid.uuid4(), enabled=False)

    async def test_raises_not_found_for_a_cross_org_id(
        self, route_service: RouteService, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        with pytest.raises(NotFoundError):
            await route_service.update(uuid.uuid4(), created.id, enabled=False)


class TestDelete:
    async def test_deletes_the_route(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        await route_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await route_service.get(organization_id, created.id)

    async def test_sets_deleted_by_from_actor_id(
        self,
        route_service: RouteService,
        routes_repo: ApiRouteRepository,
        organization_id: uuid.UUID,
        make_service,
        make_route,
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        actor_id = uuid.uuid4()
        await route_service.delete(organization_id, created.id, actor_id=str(actor_id))
        raw = await routes_repo.get_by_id(created.id, include_deleted=True)
        assert raw is not None
        assert raw.deleted_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, route_service: RouteService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await route_service.delete(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, route_service: RouteService, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        with pytest.raises(NotFoundError):
            await route_service.delete(uuid.uuid4(), created.id)


class TestResolve:
    async def test_returns_none_when_no_routes_exist(
        self, route_service: RouteService, organization_id: uuid.UUID
    ) -> None:
        found = await route_service.resolve(organization_id, method="GET", path="/anything")
        assert found is None

    async def test_returns_the_matching_route(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id, path_pattern="/orders/*", methods=["get"])
        found = await route_service.resolve(organization_id, method="GET", path="/orders/123")
        assert found is not None
        assert found.id == created.id

    async def test_prefers_lower_priority_number(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id, name="low-priority", path_pattern="/orders", priority=50)
        high_priority = await make_route(
            service.id, name="high-priority", path_pattern="/orders", priority=1
        )
        found = await route_service.resolve(organization_id, method="GET", path="/orders")
        assert found is not None
        assert found.id == high_priority.id

    async def test_falls_back_when_nothing_else_matches(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/orders")
        fallback = await make_route(
            service.id, name="fallback", path_pattern="/**", is_fallback=True
        )

        found = await route_service.resolve(organization_id, method="GET", path="/unrelated/path")
        assert found is not None
        assert found.id == fallback.id

    async def test_returns_none_when_nothing_matches_and_no_fallback(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/orders")
        found = await route_service.resolve(organization_id, method="GET", path="/unrelated")
        assert found is None

    async def test_respects_method_filter(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/orders", methods=["post"])
        found = await route_service.resolve(organization_id, method="GET", path="/orders")
        assert found is None

    async def test_respects_host_pattern(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await route_service.create(
            organization_id,
            service_id=service.id,
            name="host-route",
            path_pattern="/orders",
            methods=["get"],
            host_pattern="api.example.com",
        )
        no_match = await route_service.resolve(
            organization_id, method="GET", path="/orders", host="other.example.com"
        )
        assert no_match is None

        match = await route_service.resolve(
            organization_id, method="GET", path="/orders", host="api.example.com"
        )
        assert match is not None
        assert match.id == created.id

    async def test_respects_header_match(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await route_service.create(
            organization_id,
            service_id=service.id,
            name="header-route",
            path_pattern="/orders",
            methods=["get"],
            header_match={"x-api-version": "2"},
        )
        no_match = await route_service.resolve(
            organization_id, method="GET", path="/orders", headers={"x-api-version": "1"}
        )
        assert no_match is None

        match = await route_service.resolve(
            organization_id, method="GET", path="/orders", headers={"x-api-version": "2"}
        )
        assert match is not None
        assert match.id == created.id

    async def test_disabled_routes_are_never_candidates(
        self, route_service: RouteService, organization_id: uuid.UUID, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id, path_pattern="/orders", methods=["get"])
        await route_service.update(organization_id, created.id, enabled=False)

        found = await route_service.resolve(organization_id, method="GET", path="/orders")
        assert found is None

    async def test_tenant_isolation(
        self, route_service: RouteService, make_service, make_route
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/orders", methods=["get"])
        found = await route_service.resolve(uuid.uuid4(), method="GET", path="/orders")
        assert found is None


class TestApiRouteRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, routes_repo: ApiRouteRepository, make_service, make_route
    ) -> None:
        service = await make_service()
        created = await make_route(service.id)
        with pytest.raises(NotFoundError):
            await routes_repo.require_in_org(uuid.uuid4(), created.id)
