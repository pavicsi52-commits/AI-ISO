"""Throwaway smoke test verifying the test foundation against real infra.

Superseded once the full suite lands; kept only long enough to prove
`conftest.py` actually works end to end before parallel agents build on it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LoadBalancingStrategy, QuotaKind, QuotaScope, RateLimitScope
from app.services.health import HealthMonitorService
from app.services.proxy import ProxyService
from app.services.route import RouteService
from app.services.service import ServiceRegistryService
from tests.conftest import HTTP_OK, FAKE_BACKEND_URL


async def test_db_session_round_trips(
    db_session: AsyncSession, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
) -> None:
    created = await service_registry_service.register(
        organization_id, name="smoke-service", instances=[{"url": FAKE_BACKEND_URL, "weight": 100}]
    )
    fetched = await service_registry_service.get(organization_id, created.id)
    assert fetched.id == created.id
    assert fetched.name == "smoke-service"
    assert fetched.load_balancing_strategy == LoadBalancingStrategy.ROUND_ROBIN
    del db_session


async def test_route_resolution_and_proxy_round_trip(
    make_service, make_route, proxy_service: ProxyService, organization_id: uuid.UUID
) -> None:
    service = await make_service()
    await make_route(service.id, path_pattern="/echo", methods=["get"])

    result = await proxy_service.proxy(
        organization_id,
        method="GET",
        path="/echo",
        query_string=None,
        headers={"x-test": "1"},
        body=b"",
        source_ip="127.0.0.1",
        client_id=None,
        api_key_id=None,
        authenticated_user_id=None,
        auth_method=None,
    )
    assert result.status_code == HTTP_OK
    assert b"GET" in result.body


async def test_health_monitor_probes_a_real_endpoint(
    make_service, health_monitor_service: HealthMonitorService, organization_id: uuid.UUID
) -> None:
    """`shared_core.monitoring.checks.check_http_reachable` builds its own
    `httpx.AsyncClient` internally (confirmed by reading its source) --
    unlike `ProxyService`, it cannot be pointed at the ASGI-mounted fake
    backend. Probing therefore targets a real, already-running container
    from the standing docker-compose stack (RabbitMQ's management UI)
    rather than an unmocked call to nothing.
    """
    service = await make_service(name="probed-service")
    probed = await health_monitor_service.probe(
        organization_id, service.id, "http://127.0.0.1:15672/", service_name=service.name
    )
    assert probed.status.value == "healthy"


async def test_rate_limit_and_quota_policies_persist(
    make_rate_limit_policy, make_quota_policy
) -> None:
    rate_policy = await make_rate_limit_policy(scope=RateLimitScope.ORGANIZATION, max_requests=10)
    assert rate_policy.max_requests == 10

    quota_policy = await make_quota_policy(
        scope=QuotaScope.ORGANIZATION, kind=QuotaKind.REQUEST, limit_value=100
    )
    assert quota_policy.limit_value == 100


async def test_api_key_lifecycle(make_api_key, api_key_service, organization_id: uuid.UUID) -> None:
    raw_key, created = await make_api_key(scopes=["gateway:read"])
    verified = await api_key_service.verify(raw_key)
    assert verified.id == created.id

    new_raw_key, rotated = await api_key_service.rotate(organization_id, created.id)
    assert new_raw_key != raw_key
    with pytest.raises(Exception):  # noqa: B017 -- the old raw key must no longer verify
        await api_key_service.verify(raw_key)
    verified_after_rotation = await api_key_service.verify(new_raw_key)
    assert verified_after_rotation.id == rotated.id


async def test_http_app_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == HTTP_OK


async def test_route_service_scoped_to_organization(
    route_service: RouteService, make_service, make_route, organization_id: uuid.UUID
) -> None:
    service = await make_service()
    await make_route(service.id)
    other_org = uuid.uuid4()
    routes_for_other_org = await route_service.list_routes(other_org)
    assert routes_for_other_org == []
