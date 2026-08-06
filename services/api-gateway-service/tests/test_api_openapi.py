"""``GET /gateway/openapi`` -- the synthesized OpenAPI catalog (docs/056
"REST APIs"), built directly from this gateway's own routing table.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestGatewayOpenApi:
    async def test_an_organization_with_no_routes_has_an_empty_catalog(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["openapi"] == "3.0.3"
        assert data["paths"] == {}

    async def test_a_route_with_two_methods_produces_two_operations_tagged_by_service(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="orders-service")
        await make_route(
            service.id,
            name="list-orders",
            path_pattern="/orders",
            methods=["get", "post"],
            description="List or create orders",
        )

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        data = response.json()["data"]
        operations = data["paths"]["/orders"]
        assert set(operations) == {"get", "post"}
        assert operations["get"]["summary"] == "List or create orders"
        assert operations["get"]["operationId"] == "list-orders_get"
        assert operations["get"]["tags"] == ["orders-service"]
        assert (
            operations["get"]["responses"]["200"]["description"] == "Successful proxied response."
        )

    async def test_a_route_with_no_description_falls_back_to_its_own_name(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, name="undocumented-route", path_pattern="/undocumented")

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        operations = response.json()["data"]["paths"]["/undocumented"]
        assert operations["get"]["summary"] == "undocumented-route"

    async def test_a_route_with_no_methods_falls_back_to_get_only(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        route_service,
        organization_id: uuid.UUID,
    ) -> None:
        # `make_route` substitutes its own default (`["get", "post"]`)
        # for a falsy `methods=[]`, same as the service layer's own
        # `methods or [...]` -- so an actually-empty list is only
        # reachable by editing the row afterwards, through `update()`'s
        # `value is not None` check (`[]` is not `None`).
        service = await make_service()
        route = await make_route(service.id, name="bare-route", path_pattern="/bare")
        await route_service.update(organization_id, route.id, methods=[])

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        operations = response.json()["data"]["paths"]["/bare"]
        assert set(operations) == {"get"}

    async def test_a_disabled_route_is_excluded_from_the_catalog(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        route_service,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, name="disabled-route", path_pattern="/disabled")
        await route_service.update(organization_id, route.id, enabled=False)

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        assert "/disabled" not in response.json()["data"]["paths"]

    async def test_a_route_whose_service_was_deregistered_still_appears_with_no_tags(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        service_registry_service,
        organization_id: uuid.UUID,
    ) -> None:
        # The route survives its own service's deregistration -- the
        # catalog builder's own `service_rows.get(...)` lookup then
        # misses, so the operation is still listed, just untagged.
        service = await make_service(name="soon-gone-service")
        await make_route(service.id, name="orphaned-route", path_pattern="/orphaned")
        await service_registry_service.delete(organization_id, service.id)

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        operations = response.json()["data"]["paths"]["/orphaned"]
        assert operations["get"]["tags"] == []

    async def test_multiple_routes_produce_multiple_paths(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, name="route-a", path_pattern="/a")
        await make_route(service.id, name="route-b", path_pattern="/b")

        response = await client.get(
            "/gateway/openapi", params={"organization_id": str(organization_id)}
        )
        assert set(response.json()["data"]["paths"]) == {"/a", "/b"}
