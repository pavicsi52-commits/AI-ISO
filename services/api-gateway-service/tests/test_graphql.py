"""The GraphQL query surface (docs/056), mounted at ``/graphql``.

No existing precedent in this monorepo to mirror -- driven directly over
HTTP with ``httpx``/the ``client`` fixture, posting ``{"query": "..."}``
and asserting on ``response.json()["data"]``. Every actual POST to
``/graphql`` also exercises ``app/api/graphql_router.py``'s own
``get_graphql_context`` (strawberry's FastAPI integration wraps it as a
dependency and calls it per request), so no separate unit test of that
function is needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.request import ApiRequestLog, ApiResponseLog
from app.services.reporting import StatisticsService

pytestmark = pytest.mark.asyncio


async def _graphql(client: AsyncClient, query: str) -> dict:
    response = await client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    body = response.json()
    assert "errors" not in body, body.get("errors")
    return body["data"]


class TestServicesQuery:
    async def test_returns_every_registered_service(
        self, client: AsyncClient, make_service, organization_id: uuid.UUID
    ) -> None:
        await make_service(name="orders-svc")
        await make_service(name="billing-svc")

        data = await _graphql(
            client,
            f'{{ services(organizationId: "{organization_id}") '
            "{ name enabled instanceCount loadBalancingStrategy healthCheckPath } }",
        )
        names = {row["name"] for row in data["services"]}
        assert names == {"orders-svc", "billing-svc"}
        for row in data["services"]:
            assert row["enabled"] is True
            assert row["instanceCount"] == 1
            assert row["loadBalancingStrategy"] == "round_robin"
            assert row["healthCheckPath"] == "/health"

    async def test_an_organization_with_no_services_returns_an_empty_list(
        self, client: AsyncClient
    ) -> None:
        data = await _graphql(client, f'{{ services(organizationId: "{uuid.uuid4()}") {{ id }} }}')
        assert data["services"] == []

    async def test_enabled_filter_narrows_the_result(
        self,
        client: AsyncClient,
        make_service,
        service_registry_service,
        organization_id: uuid.UUID,
    ) -> None:
        active = await make_service(name="active-svc")
        disabled = await make_service(name="disabled-svc")
        await service_registry_service.update(organization_id, disabled.id, enabled=False)

        enabled_only = await _graphql(
            client, f'{{ services(organizationId: "{organization_id}", enabled: true) {{ name }} }}'
        )
        assert [row["name"] for row in enabled_only["services"]] == [active.name]

        disabled_only = await _graphql(
            client,
            f'{{ services(organizationId: "{organization_id}", enabled: false) {{ name }} }}',
        )
        assert [row["name"] for row in disabled_only["services"]] == [disabled.name]


class TestRoutesQuery:
    async def test_returns_every_configured_route(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, name="route-one", path_pattern="/one")
        await make_route(service.id, name="route-two", path_pattern="/two")

        data = await _graphql(
            client,
            f'{{ routes(organizationId: "{organization_id}") '
            "{ name pathPattern methods priority enabled matchKind } }",
        )
        names = {row["name"] for row in data["routes"]}
        assert names == {"route-one", "route-two"}
        for row in data["routes"]:
            assert row["enabled"] is True
            assert row["matchKind"] == "path"

    async def test_an_organization_with_no_routes_returns_an_empty_list(
        self, client: AsyncClient
    ) -> None:
        data = await _graphql(client, f'{{ routes(organizationId: "{uuid.uuid4()}") {{ id }} }}')
        assert data["routes"] == []

    async def test_service_id_filter_narrows_the_result(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service_a = await make_service(name="svc-a")
        service_b = await make_service(name="svc-b")
        await make_route(service_a.id, name="route-a", path_pattern="/a")
        await make_route(service_b.id, name="route-b", path_pattern="/b")

        data = await _graphql(
            client,
            f'{{ routes(organizationId: "{organization_id}", serviceId: "{service_a.id}") '
            "{ name serviceId } }",
        )
        assert [row["name"] for row in data["routes"]] == ["route-a"]
        assert data["routes"][0]["serviceId"] == str(service_a.id)


class TestStatisticsQuery:
    async def test_with_no_rolled_up_window_every_field_is_null(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        data = await _graphql(
            client,
            f'{{ statistics(organizationId: "{organization_id}") '
            "{ errorRate successRate averageLatencyMs p95LatencyMs computedThrough } }",
        )
        assert data["statistics"] == {
            "errorRate": None,
            "successRate": None,
            "averageLatencyMs": None,
            "p95LatencyMs": None,
            "computedThrough": None,
        }

    async def test_after_a_rollup_the_latest_window_is_returned(
        self,
        client: AsyncClient,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        request = await request_logs_repo.create(
            ApiRequestLog(
                organization_id=organization_id,
                method="GET",
                path="/echo",
                correlation_id=str(uuid.uuid4()),
                started_at=now,
            )
        )
        await response_logs_repo.create(
            ApiResponseLog(
                organization_id=organization_id,
                request_id=request.id,
                status_code=200,
                latency_ms=42.0,
                completed_at=now,
            )
        )
        await statistics_service.rollup(
            organization_id,
            window_start=now - timedelta(hours=1),
            window_end=now + timedelta(hours=1),
        )

        data = await _graphql(
            client,
            f'{{ statistics(organizationId: "{organization_id}") {{ successRate errorRate }} }}',
        )
        assert data["statistics"]["successRate"] == 100.0
        assert data["statistics"]["errorRate"] == 0.0
