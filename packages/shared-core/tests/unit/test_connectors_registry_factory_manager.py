"""Tests for registry.py, factory.py, manager.py, and helpers.py."""

from __future__ import annotations

import pytest
from shared_core.connectors.base import (
    BaseConnector,
    CommandResult,
    ConnectorCapability,
)
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import username_password
from shared_core.connectors.decorators import connector, get_provider_name
from shared_core.connectors.discovery import DiscoveryResult
from shared_core.connectors.exceptions import ProviderNotRegisteredError
from shared_core.connectors.factory import (
    build_connector_factory,
    create_connected_connector,
    create_connector,
)
from shared_core.connectors.health import ConnectorHealthReport, build_health_report
from shared_core.connectors.helpers import connector_summary, format_bytes
from shared_core.connectors.inventory import InventoryReport
from shared_core.connectors.manager import ConnectorManager
from shared_core.connectors.registry import ConnectorRegistry


@connector("fake")
class _FakeConnector(BaseConnector):
    capabilities = frozenset({ConnectorCapability.EXECUTE})

    async def connect(self) -> None:
        self.state = ConnectionState.CONNECTED
        self.record_connection()

    async def disconnect(self) -> None:
        self.state = ConnectionState.DISCONNECTED

    async def validate(self) -> bool:
        return True

    async def execute(self, command: str, **kwargs: object) -> CommandResult:
        return CommandResult(command=command, exit_code=0)

    async def health(self) -> ConnectorHealthReport:
        return build_health_report(
            connection_state=self.state, authenticated=True, protocol_ok=True
        )

    async def collect_inventory(self) -> InventoryReport:
        return InventoryReport(host=self.config.host)

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(host=self.config.host, reachable=True)


class _UndecoratedConnector(BaseConnector):
    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def validate(self) -> bool:
        return True

    async def execute(self, command: str, **kwargs: object) -> CommandResult:
        return CommandResult(command=command, exit_code=0)

    async def health(self) -> ConnectorHealthReport:
        return build_health_report(
            connection_state=self.state, authenticated=True, protocol_ok=True
        )

    async def collect_inventory(self) -> InventoryReport:
        return InventoryReport(host=self.config.host)

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(host=self.config.host, reachable=True)


def _config(host: str = "10.0.0.1") -> ConnectionConfig:
    return ConnectionConfig(host=host)


def _credential() -> object:
    return username_password("admin", "hunter2")


# --- registry.py ---


def test_register_then_get_round_trips() -> None:
    registry = ConnectorRegistry()

    registry.register("fake", _FakeConnector)

    assert registry.get("fake") is _FakeConnector


def test_get_raises_for_an_unregistered_provider() -> None:
    registry = ConnectorRegistry()

    with pytest.raises(ProviderNotRegisteredError):
        registry.get("missing")


def test_register_decorated_uses_the_decorator_attached_name() -> None:
    registry = ConnectorRegistry()

    registry.register_decorated(_FakeConnector)

    assert registry.is_registered("fake") is True
    assert registry.get("fake") is _FakeConnector


def test_register_decorated_rejects_an_undecorated_class() -> None:
    registry = ConnectorRegistry()

    with pytest.raises(ValueError, match="was not decorated"):
        registry.register_decorated(_UndecoratedConnector)


def test_unregister_removes_the_provider() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)

    registry.unregister("fake")

    assert registry.is_registered("fake") is False


def test_unregister_unknown_provider_is_a_no_op() -> None:
    registry = ConnectorRegistry()

    registry.unregister("missing")


def test_list_providers_returns_every_registered_name() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)

    assert registry.list_providers() == ["fake"]


def test_get_provider_name_matches_the_decorator() -> None:
    assert get_provider_name(_FakeConnector) == "fake"
    assert _FakeConnector.provider_name == "fake"


# --- factory.py ---


def test_create_connector_builds_an_uninstantiated_instance() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)

    instance = create_connector(registry, "fake", _config(), _credential())  # type: ignore[arg-type]

    assert isinstance(instance, _FakeConnector)
    assert instance.state == ConnectionState.DISCONNECTED


async def test_create_connected_connector_connects_immediately() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)

    instance = await create_connected_connector(
        registry, "fake", _config(), _credential()  # type: ignore[arg-type]
    )

    assert instance.state == ConnectionState.CONNECTED


async def test_build_connector_factory_produces_a_connected_instance() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)
    factory = build_connector_factory(registry, "fake", _config(), _credential())  # type: ignore[arg-type]

    instance = await factory()

    assert isinstance(instance, _FakeConnector)
    assert instance.state == ConnectionState.CONNECTED


# --- manager.py ---


async def test_manager_get_connector_creates_and_connects() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)
    manager = ConnectorManager(registry)

    instance = await manager.get_connector("fake", _config(), _credential())  # type: ignore[arg-type]

    assert instance.state == ConnectionState.CONNECTED
    assert manager.pool_count() == 1


async def test_manager_reuses_the_pool_for_the_same_provider_and_host() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)
    manager = ConnectorManager(registry)

    first = await manager.get_connector("fake", _config(), _credential())  # type: ignore[arg-type]
    await manager.release_connector("fake", _config(), first)
    second = await manager.get_connector("fake", _config(), _credential())  # type: ignore[arg-type]

    assert second is first
    assert manager.pool_count() == 1


async def test_manager_release_connector_for_an_unknown_pool_is_a_no_op() -> None:
    manager = ConnectorManager()

    await manager.release_connector("fake", _config(), _FakeConnector(_config(), _credential()))  # type: ignore[arg-type]


async def test_manager_close_disconnects_and_clears_pools() -> None:
    registry = ConnectorRegistry()
    registry.register("fake", _FakeConnector)
    manager = ConnectorManager(registry)
    instance = await manager.get_connector("fake", _config(), _credential())  # type: ignore[arg-type]
    await manager.release_connector("fake", _config(), instance)

    await manager.close()

    assert manager.pool_count() == 0


def test_manager_defaults_to_a_fresh_registry() -> None:
    manager = ConnectorManager()

    assert manager.registry.list_providers() == []


# --- helpers.py ---


def test_format_bytes_under_one_kb() -> None:
    assert format_bytes(512) == "512 B"


def test_format_bytes_in_kb() -> None:
    assert format_bytes(2048) == "2.0 KB"


def test_format_bytes_in_mb() -> None:
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_format_bytes_in_gb() -> None:
    assert format_bytes(3 * 1024**3) == "3.0 GB"


async def test_connector_summary_omits_credentials_and_reports_state() -> None:
    instance = _FakeConnector(_config(), _credential())  # type: ignore[arg-type]
    await instance.connect()

    summary = connector_summary(instance)

    assert summary["provider"] == "fake"
    assert summary["host"] == "10.0.0.1"
    assert summary["state"] == "connected"
    assert summary["connection_count"] == 1
    assert "credential" not in summary
