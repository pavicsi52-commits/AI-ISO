"""Tests for base.py, discovery.py, health.py, inventory.py, and validation.py."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.connectors.base import (
    BaseConnector,
    CommandResult,
    ConnectorCapability,
)
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import Credential, CredentialType, username_password
from shared_core.connectors.discovery import DiscoveryResult, discover_host, discover_ports
from shared_core.connectors.exceptions import CapabilityNotSupportedError, ConnectorValidationError
from shared_core.connectors.health import (
    ConnectorHealthReport,
    build_health_report,
    connection_state_to_health,
)
from shared_core.connectors.inventory import InventoryReport
from shared_core.connectors.validation import (
    validate_capability,
    validate_certificate_expiry,
    validate_connection_config,
    validate_credential,
    validate_schema,
)
from shared_core.enums.health_status import HealthStatus


class _FakeConnector(BaseConnector):
    """Minimal concrete subclass proving `BaseConnector`'s own generic mechanics."""

    provider_name = "fake"
    capabilities = frozenset({ConnectorCapability.EXECUTE})

    def __init__(self, config: ConnectionConfig, credential: object) -> None:
        super().__init__(config, credential)  # type: ignore[arg-type]
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        self.record_connection()
        self.state = ConnectionState.CONNECTED

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.state = ConnectionState.DISCONNECTED

    async def validate(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    async def execute(self, command: str, **kwargs: object) -> CommandResult:
        return CommandResult(command=command, exit_code=0, stdout="ok")

    async def health(self) -> ConnectorHealthReport:
        return build_health_report(
            connection_state=self.state, authenticated=True, protocol_ok=True
        )

    async def collect_inventory(self) -> InventoryReport:
        return InventoryReport(host=self.config.host)

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(host=self.config.host, reachable=True)


def _connector() -> _FakeConnector:
    return _FakeConnector(ConnectionConfig(host="10.0.0.1"), username_password("admin", "hunter2"))


# --- base.py ---


async def test_connect_transitions_to_connected() -> None:
    connector = _connector()

    await connector.connect()

    assert connector.state == ConnectionState.CONNECTED
    assert connector.connect_calls == 1


async def test_reconnect_disconnects_then_connects_when_already_connected() -> None:
    connector = _connector()
    await connector.connect()

    await connector.reconnect()

    assert connector.disconnect_calls == 1
    assert connector.connect_calls == 2
    assert connector.state == ConnectionState.CONNECTED


async def test_reconnect_skips_disconnect_when_never_connected() -> None:
    connector = _connector()

    await connector.reconnect()

    assert connector.disconnect_calls == 0
    assert connector.connect_calls == 1


async def test_execute_returns_a_command_result() -> None:
    connector = _connector()

    result = await connector.execute("echo hi")

    assert result.succeeded is True
    assert result.stdout == "ok"


def test_command_result_succeeded_false_for_nonzero_exit() -> None:
    result = CommandResult(command="false", exit_code=1)

    assert result.succeeded is False


def test_describe_capabilities_and_supports() -> None:
    connector = _connector()

    assert connector.describe_capabilities() == frozenset({ConnectorCapability.EXECUTE})
    assert connector.supports(ConnectorCapability.EXECUTE) is True
    assert connector.supports(ConnectorCapability.FILE_TRANSFER) is False


def test_metrics_starts_at_zero() -> None:
    connector = _connector()

    snapshot = connector.metrics()

    assert snapshot.connection_count == 0
    assert snapshot.success_count == 0


async def test_metrics_track_connection_success_failure_retry() -> None:
    connector = _connector()

    await connector.connect()
    connector.record_success(latency_ms=12.5)
    connector.record_failure()
    connector.record_retry()

    snapshot = connector.metrics()
    assert snapshot.connection_count == 1
    assert snapshot.success_count == 1
    assert snapshot.failure_count == 1
    assert snapshot.retry_count == 1
    assert snapshot.last_latency_ms == 12.5


def test_base_connector_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        BaseConnector(ConnectionConfig(host="x"), username_password("a", "b"))  # type: ignore[abstract]


# --- discovery.py, against real throwaway sockets ---


async def _accept_and_close(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.close()
    await writer.wait_closed()


@pytest.fixture
async def open_port() -> AsyncIterator[int]:
    server = await asyncio.start_server(_accept_and_close, host="127.0.0.1", port=0)
    port: int = server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def _closed_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    sock.close()
    return port


async def test_discover_ports_reports_an_open_port(open_port: int) -> None:
    result = await discover_ports("127.0.0.1", [open_port], timeout_seconds=2)

    assert result[0].open is True


async def test_discover_ports_reports_a_closed_port() -> None:
    port = _closed_port()

    result = await discover_ports("127.0.0.1", [port], timeout_seconds=2)

    assert result[0].open is False


async def test_discover_host_reachable_true_when_a_port_is_open(open_port: int) -> None:
    result = await discover_host("127.0.0.1", ports=[open_port], timeout_seconds=2)

    assert result.reachable is True


async def test_discover_host_reachable_false_with_no_ports_given() -> None:
    result = await discover_host("127.0.0.1", timeout_seconds=2)

    assert result.reachable is False
    assert result.ports == ()


# --- health.py ---


def test_connection_state_to_health_mapping() -> None:
    assert connection_state_to_health(ConnectionState.CONNECTED) == HealthStatus.HEALTHY
    assert connection_state_to_health(ConnectionState.FAILED) == HealthStatus.UNHEALTHY
    assert connection_state_to_health(ConnectionState.DISCONNECTED) == HealthStatus.UNKNOWN


def test_build_health_report_healthy_when_everything_ok() -> None:
    report = build_health_report(
        connection_state=ConnectionState.CONNECTED, authenticated=True, protocol_ok=True
    )

    assert report.status == HealthStatus.HEALTHY


def test_build_health_report_unhealthy_when_authentication_failed() -> None:
    report = build_health_report(
        connection_state=ConnectionState.CONNECTED, authenticated=False, protocol_ok=True
    )

    assert report.status == HealthStatus.UNHEALTHY
    assert report.authentication_status == HealthStatus.UNHEALTHY


# --- inventory.py ---


def test_inventory_report_defaults_are_empty() -> None:
    report = InventoryReport(host="10.0.0.1")

    assert report.hardware == {}
    assert report.storage == ()
    assert report.collected_at is not None


# --- validation.py ---


def test_validate_connection_config_accepts_a_valid_config() -> None:
    validate_connection_config(ConnectionConfig(host="10.0.0.1", port=22))


def test_validate_connection_config_rejects_an_empty_host() -> None:
    with pytest.raises(ConnectorValidationError):
        validate_connection_config(ConnectionConfig(host="   "))


def test_validate_connection_config_rejects_an_invalid_port() -> None:
    with pytest.raises(ConnectorValidationError):
        validate_connection_config(ConnectionConfig(host="10.0.0.1", port=70000))


def test_validate_connection_config_rejects_a_non_positive_timeout() -> None:
    config = ConnectionConfig(host="10.0.0.1")
    object.__setattr__(config, "connect_timeout_seconds", 0)

    with pytest.raises(ConnectorValidationError):
        validate_connection_config(config)


def test_validate_credential_accepts_a_complete_credential() -> None:
    validate_credential(username_password("admin", "hunter2"))


def test_validate_credential_rejects_a_missing_secret() -> None:
    credential = Credential(credential_type=CredentialType.USERNAME_PASSWORD, identity="admin")

    with pytest.raises(ConnectorValidationError):
        validate_credential(credential)


def test_validate_credential_ignores_unlisted_credential_types() -> None:
    validate_credential(Credential(credential_type=CredentialType.KERBEROS))


def test_validate_certificate_expiry_accepts_a_future_date() -> None:
    validate_certificate_expiry(datetime.now(UTC) + timedelta(days=1))


def test_validate_certificate_expiry_rejects_a_past_date() -> None:
    with pytest.raises(ConnectorValidationError):
        validate_certificate_expiry(datetime.now(UTC) - timedelta(days=1))


def test_validate_capability_accepts_a_supported_capability() -> None:
    validate_capability("execute", frozenset({"execute", "discovery"}))


def test_validate_capability_rejects_an_unsupported_capability() -> None:
    with pytest.raises(CapabilityNotSupportedError):
        validate_capability("file_transfer", frozenset({"execute"}))


def test_validate_schema_accepts_a_complete_payload() -> None:
    validate_schema({"host": "x", "port": 22}, ["host", "port"])


def test_validate_schema_rejects_a_missing_field() -> None:
    with pytest.raises(ConnectorValidationError):
        validate_schema({"host": "x"}, ["host", "port"])
