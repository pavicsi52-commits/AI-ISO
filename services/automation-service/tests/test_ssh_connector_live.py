"""Live tests for :class:`app.connectors.ssh_connector.SshConnector`
against a real, locally run ``linuxserver/openssh-server`` Docker
container -- matching ``services/discovery-service``'s own SSH scanner
test precedent. Started via::

    docker run -d --name aiios_automation_test_ssh -p 2223:2222 \\
      -e PUID=1000 -e PGID=1000 -e PASSWORD_ACCESS=true \\
      -e USER_NAME=testuser -e USER_PASSWORD=testpass123 \\
      lscr.io/linuxserver/openssh-server:latest

A distinct host port (2223) from ``services/discovery-service``'s own
SSH test container (2222) since both could conceivably run in the same
CI environment.
"""

from __future__ import annotations

import socket

import pytest
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import username_password
from shared_core.enums.health_status import HealthStatus
from shared_core.exceptions.connector import ConnectorError

from app.connectors.ssh_connector import SshConnector

SSH_TEST_HOST = "localhost"
SSH_TEST_PORT = 2223
SSH_TEST_USERNAME = "testuser"
SSH_TEST_PASSWORD = "testpass123"


def _ssh_container_reachable() -> bool:
    try:
        with socket.create_connection((SSH_TEST_HOST, SSH_TEST_PORT), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _ssh_container_reachable(),
    reason="aiios_automation_test_ssh container is not reachable on localhost:2223.",
)


def _build_connector(*, password: str = SSH_TEST_PASSWORD) -> SshConnector:
    config = ConnectionConfig(host=SSH_TEST_HOST, port=SSH_TEST_PORT, connect_timeout_seconds=5)
    credential = username_password(SSH_TEST_USERNAME, password)
    return SshConnector(config, credential)


class TestSshConnectorLive:
    async def test_connect_and_execute_real_command(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            assert connector.state == ConnectionState.CONNECTED
            result = await connector.execute("echo hello-ssh")
            assert result.exit_code == 0
            assert "hello-ssh" in result.stdout
        finally:
            await connector.disconnect()

    async def test_disconnect_resets_state(self) -> None:
        connector = _build_connector()
        await connector.connect()
        await connector.disconnect()
        assert connector.state == ConnectionState.DISCONNECTED
        assert await connector.validate() is False

    async def test_wrong_password_raises_connector_error(self) -> None:
        connector = _build_connector(password="definitely-wrong")
        with pytest.raises(ConnectorError, match="SSH connection"):
            await connector.connect()
        assert connector.state == ConnectionState.FAILED

    async def test_execute_without_connect_raises(self) -> None:
        connector = _build_connector()
        with pytest.raises(ConnectorError, match="not connected"):
            await connector.execute("echo nope")

    async def test_validate_true_while_connected(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            assert await connector.validate() is True
        finally:
            await connector.disconnect()

    async def test_health_reports_connected(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            report = await connector.health()
            assert report.authentication_status == HealthStatus.HEALTHY
            assert report.status == HealthStatus.HEALTHY
        finally:
            await connector.disconnect()

    async def test_collect_inventory_returns_uname(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            report = await connector.collect_inventory()
            assert report.host == SSH_TEST_HOST
            assert "uname" in report.operating_system
            assert report.operating_system["uname"]
        finally:
            await connector.disconnect()

    async def test_discover_reachable(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            result = await connector.discover()
            assert result.reachable is True
        finally:
            await connector.disconnect()

    async def test_nonzero_exit_command(self) -> None:
        connector = _build_connector()
        await connector.connect()
        try:
            result = await connector.execute("exit 7")
            assert result.exit_code == 7
        finally:
            await connector.disconnect()


__all__ = ["SSH_TEST_HOST", "SSH_TEST_PASSWORD", "SSH_TEST_PORT", "SSH_TEST_USERNAME"]
