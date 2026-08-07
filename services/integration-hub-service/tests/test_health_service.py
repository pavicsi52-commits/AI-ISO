"""HealthService.probe(): the automated connector health-probe cycle.

Reuses the same real HTTP/TCP reachability primitives as
``ConnectionService`` (see ``tests/conftest.py``'s own docstring for why
they cannot be pointed at a test double), writing to ``connector_health``
instead of ``connector_connections``.
"""

from __future__ import annotations

import uuid

from shared_core.enums.health_status import HealthStatus

from app.config.settings import IntegrationHubServiceSettings
from app.services.connector import ConnectorService
from app.services.health import HealthService
from tests.conftest import (
    REACHABLE_HTTP_URL,
    REACHABLE_TCP_HOST,
    REACHABLE_TCP_PORT,
    UNREACHABLE_HTTP_URL,
    UNREACHABLE_TCP_HOST,
    UNREACHABLE_TCP_PORT,
)


class TestHttpProbe:
    async def test_a_reachable_http_endpoint_is_healthy(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.HEALTHY
        assert result.error is None

    async def test_an_unreachable_http_endpoint_is_unhealthy(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": UNREACHABLE_HTTP_URL}
        )
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.UNHEALTHY
        assert result.error is not None


class TestTcpProbe:
    async def test_a_reachable_tcp_host_and_port_is_healthy(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id,
            connector.id,
            config={"host": REACHABLE_TCP_HOST, "port": REACHABLE_TCP_PORT},
        )
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.HEALTHY
        assert result.error is None

    async def test_an_unreachable_tcp_host_and_port_is_unhealthy(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id,
            connector.id,
            config={"host": UNREACHABLE_TCP_HOST, "port": UNREACHABLE_TCP_PORT},
        )
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.UNHEALTHY
        assert result.error is not None


class TestUnknownProbe:
    async def test_a_connector_with_no_checkable_endpoint_is_unknown_not_a_crash(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"api_version": "v1"}
        )
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.UNKNOWN
        assert result.error == "No checkable endpoint_url or host/port configured."

    async def test_a_connector_with_no_configuration_at_all_is_unknown_not_a_crash(
        self, health_service: HealthService, make_connector
    ) -> None:
        connector = await make_connector()
        result = await health_service.probe(connector)
        assert result.status == HealthStatus.UNKNOWN
        assert result.error is not None


class TestConsecutiveFailures:
    async def test_increments_from_the_connectors_own_current_count_on_failure(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": UNREACHABLE_HTTP_URL}
        )
        connector.consecutive_failures = 2
        result = await health_service.probe(connector)
        assert result.consecutive_failures == 3

    async def test_resets_to_zero_on_success_regardless_of_the_prior_count(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        connector.consecutive_failures = 5
        result = await health_service.probe(connector)
        assert result.consecutive_failures == 0


class TestRecoveryAttempted:
    async def test_is_true_once_the_about_to_be_recorded_failure_count_reaches_the_threshold(
        self,
        health_service: HealthService,
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": UNREACHABLE_HTTP_URL}
        )
        connector.consecutive_failures = service_settings.health_failure_threshold - 1
        result = await health_service.probe(connector)
        assert result.consecutive_failures == service_settings.health_failure_threshold
        assert result.recovery_attempted is True

    async def test_is_false_while_still_below_the_threshold(
        self,
        health_service: HealthService,
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": UNREACHABLE_HTTP_URL}
        )
        connector.consecutive_failures = 0
        result = await health_service.probe(connector)
        assert result.consecutive_failures < service_settings.health_failure_threshold
        assert result.recovery_attempted is False

    async def test_is_false_on_success_even_with_a_high_prior_failure_count(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        connector.consecutive_failures = 10
        result = await health_service.probe(connector)
        assert result.recovery_attempted is False


class TestListAndLatestForConnector:
    async def test_list_for_connector_returns_newest_first(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        first = await health_service.probe(connector)
        second = await health_service.probe(connector)
        listed = await health_service.list_for_connector(connector.id)
        assert [row.id for row in listed] == [second.id, first.id]

    async def test_list_for_connector_respects_the_limit(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        await health_service.probe(connector)
        await health_service.probe(connector)
        listed = await health_service.list_for_connector(connector.id, limit=1)
        assert len(listed) == 1

    async def test_latest_for_connector_returns_the_most_recent_check(
        self,
        health_service: HealthService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        await health_service.probe(connector)
        second = await health_service.probe(connector)
        latest = await health_service.latest_for_connector(connector.id)
        assert latest is not None
        assert latest.id == second.id

    async def test_latest_for_connector_returns_none_when_no_checks_exist(
        self, health_service: HealthService, make_connector
    ) -> None:
        connector = await make_connector()
        assert await health_service.latest_for_connector(connector.id) is None
