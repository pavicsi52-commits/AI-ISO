"""ConnectionService.test(): the caller-triggered "test this connection" probe.

Against real PostgreSQL for persistence, and the real HTTP/TCP
reachability primitives in ``shared_core.monitoring.checks`` -- which
build their own internal ``httpx.AsyncClient`` and cannot be pointed at
a test double at all (see ``tests/conftest.py``'s own docstring). Every
probe here runs against an already-running container from the standing
docker-compose stack (``REACHABLE_*``) or a real loopback port nothing
listens on (``UNREACHABLE_*``) -- never mocked.
"""

from __future__ import annotations

import uuid

from app.models.enums import ConnectionStatus
from app.repositories.credential import ConnectorConnectionRepository
from app.services.connection import ConnectionService
from app.services.connector import ConnectorService
from tests.conftest import (
    REACHABLE_HTTP_URL,
    REACHABLE_TCP_HOST,
    REACHABLE_TCP_PORT,
    UNREACHABLE_HTTP_URL,
    UNREACHABLE_TCP_HOST,
    UNREACHABLE_TCP_PORT,
)


class TestHttpProbe:
    async def test_a_reachable_http_endpoint_succeeds(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.SUCCESS
        assert result.error is None
        assert result.response_metadata == {"checked": "http", "url": REACHABLE_HTTP_URL}

    async def test_an_unreachable_http_endpoint_fails_with_an_error(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": UNREACHABLE_HTTP_URL}
        )
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.FAILED
        assert result.error is not None
        assert result.response_metadata == {"checked": "http", "url": UNREACHABLE_HTTP_URL}


class TestTcpProbe:
    async def test_a_reachable_tcp_host_and_port_succeeds(
        self,
        connection_service: ConnectionService,
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
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.SUCCESS
        assert result.error is None
        assert result.response_metadata == {
            "checked": "tcp",
            "host": REACHABLE_TCP_HOST,
            "port": REACHABLE_TCP_PORT,
        }

    async def test_an_unreachable_tcp_host_and_port_fails(
        self,
        connection_service: ConnectionService,
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
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.FAILED
        assert result.error is not None


class TestStructuralProbe:
    async def test_no_configuration_fails_with_a_configuration_error(
        self, connection_service: ConnectionService, make_connector
    ) -> None:
        connector = await make_connector()
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.FAILED
        assert result.error is not None
        assert "configuration" in result.error

    async def test_no_configuration_fails_even_with_an_active_credential(
        self, connection_service: ConnectionService, make_connector
    ) -> None:
        connector = await make_connector()
        result = await connection_service.test(connector, has_active_credential=False)
        assert result.status == ConnectionStatus.FAILED
        assert result.error is not None
        assert "configuration" in result.error

    async def test_configuration_without_an_active_credential_fails_with_a_credential_error(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"api_version": "v1"}
        )
        result = await connection_service.test(connector, has_active_credential=False)
        assert result.status == ConnectionStatus.FAILED
        assert result.error is not None
        assert "configuration" not in result.error
        assert "active credential" in result.error

    async def test_configuration_with_an_active_credential_succeeds(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"api_version": "v1"}
        )
        result = await connection_service.test(connector, has_active_credential=True)
        assert result.status == ConnectionStatus.SUCCESS
        assert result.error is None
        assert result.response_metadata == {"checked": "structural"}


class TestAttemptNumber:
    async def test_increments_across_repeated_calls_for_the_same_connector(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"api_version": "v1"}
        )
        first = await connection_service.test(connector, has_active_credential=True)
        second = await connection_service.test(connector, has_active_credential=True)
        third = await connection_service.test(connector, has_active_credential=True)
        assert first.attempt_number == 1
        assert second.attempt_number == 2
        assert third.attempt_number == 3

    async def test_attempt_numbering_is_independent_per_connector(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector_a = await connector_service.configure(
            organization_id, (await make_connector("connector-a")).id, config={"api_version": "v1"}
        )
        connector_b = await connector_service.configure(
            organization_id, (await make_connector("connector-b")).id, config={"api_version": "v1"}
        )
        await connection_service.test(connector_a, has_active_credential=True)
        first_b = await connection_service.test(connector_b, has_active_credential=True)
        assert first_b.attempt_number == 1


class TestPersistence:
    async def test_every_attempt_is_persisted_and_retrievable(
        self,
        connection_service: ConnectionService,
        connector_service: ConnectorService,
        connections_repo: ConnectorConnectionRepository,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        connector = await make_connector()
        connector = await connector_service.configure(
            organization_id, connector.id, config={"api_version": "v1"}
        )
        credential = await make_credential(connector.id)

        recorded = await connection_service.test(
            connector, credential_id=credential.id, has_active_credential=True
        )

        listed = await connections_repo.list_for_connector(connector.id)
        assert [row.id for row in listed] == [recorded.id]
        assert listed[0].status == ConnectionStatus.SUCCESS
        assert listed[0].credential_id == credential.id
        assert listed[0].organization_id == organization_id
        assert listed[0].connector_id == connector.id
        assert listed[0].attempt_number == 1

        await connection_service.test(connector, has_active_credential=True)
        listed_after_second = await connections_repo.list_for_connector(connector.id)
        assert len(listed_after_second) == 2
        # Newest first.
        assert listed_after_second[0].attempt_number == 2
