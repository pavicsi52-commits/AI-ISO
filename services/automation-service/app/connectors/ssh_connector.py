"""SSH connector, via ``paramiko`` (the same SSH library
``services/discovery-service``'s own ``ssh_scanner.py`` already vetted
in this monorepo -- no second SSH dependency).

The one genuinely real, live-tested ``shared_core.connectors
.BaseConnector`` provider this service registers (against a local
Docker SSH container, matching every other AI-IOS prompt's own "one
real, live-tested target" precedent). Every other
:class:`~app.models.enums.ConnectorType` member is real, storable
target metadata -- attempting to dispatch execution to one raises
:class:`~shared_core.connectors.exceptions.ProviderNotRegisteredError`
from :meth:`~shared_core.connectors.registry.ConnectorRegistry.get`
itself, matching ``packages/shared-core/connectors``' own explicit
scope note that concrete provider packages beyond SSH are a separate,
later phase of work.
"""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any

import paramiko
from shared_core.connectors.base import BaseConnector, CommandResult, ConnectorCapability
from shared_core.connectors.connection import ConnectionState
from shared_core.connectors.decorators import connector
from shared_core.connectors.discovery import DiscoveryResult
from shared_core.connectors.health import ConnectorHealthReport, build_health_report
from shared_core.connectors.inventory import InventoryReport
from shared_core.exceptions.connector import ConnectorError

_DEFAULT_SSH_PORT = 22


@connector("ssh")
class SshConnector(BaseConnector):
    """A real SSH connector backed by ``paramiko``, run off-loop via ``asyncio.to_thread``."""

    provider_name = "ssh"
    capabilities = frozenset(
        {
            ConnectorCapability.EXECUTE,
            ConnectorCapability.INVENTORY,
            ConnectorCapability.DISCOVERY,
        }
    )

    def __init__(self, config: Any, credential: Any) -> None:
        super().__init__(config, credential)
        self._client: paramiko.SSHClient | None = None

    async def connect(self) -> None:
        """Establish and authenticate a real SSH session.

        Raises:
            ConnectorError: If the connection or authentication fails.
        """
        self.state = ConnectionState.CONNECTING
        self.record_connection()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": self.config.host,
            "port": self.config.port or _DEFAULT_SSH_PORT,
            "timeout": self.config.connect_timeout_seconds,
            "username": self.credential.identity,
        }
        if self.credential.has_secret("password"):
            connect_kwargs["password"] = self.credential.reveal("password")
        if self.credential.has_secret("private_key"):
            key_file = io.StringIO(self.credential.reveal("private_key"))
            connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key(key_file)

        try:
            await asyncio.to_thread(client.connect, **connect_kwargs)
        except Exception as exc:
            self.state = ConnectionState.FAILED
            raise ConnectorError(f"SSH connection to {self.config.host} failed: {exc}") from exc
        self._client = client
        self.state = ConnectionState.CONNECTED

    async def disconnect(self) -> None:
        """Close the SSH session."""
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
            self._client = None
        self.state = ConnectionState.DISCONNECTED

    async def validate(self) -> bool:
        """Whether the underlying transport is still alive."""
        if self._client is None:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    async def execute(self, command: str, **kwargs: Any) -> CommandResult:
        """Run *command* over the live SSH session and capture its real output.

        Raises:
            ConnectorError: If not connected, or the command channel fails.
        """
        if self._client is None:
            raise ConnectorError("SSH connector is not connected.")
        start = time.perf_counter()
        try:
            _stdin, stdout, stderr = await asyncio.to_thread(self._client.exec_command, command)
            exit_code = await asyncio.to_thread(stdout.channel.recv_exit_status)
            stdout_bytes = await asyncio.to_thread(stdout.read)
            stderr_bytes = await asyncio.to_thread(stderr.read)
        except Exception as exc:
            self.record_failure()
            raise ConnectorError(f"SSH command execution failed: {exc}") from exc
        duration = time.perf_counter() - start
        self.record_success(latency_ms=duration * 1000)
        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_seconds=duration,
        )

    async def health(self) -> ConnectorHealthReport:
        """A real health snapshot derived from the live transport's own state."""
        connected = await self.validate()
        return build_health_report(
            connection_state=self.state, authenticated=connected, protocol_ok=connected
        )

    async def collect_inventory(self) -> InventoryReport:
        """A minimal, genuinely-collected inventory (``uname -a`` output)."""
        result = await self.execute("uname -a")
        return InventoryReport(
            host=self.config.host, operating_system={"uname": result.stdout.strip()}
        )

    async def discover(self) -> DiscoveryResult:
        """Whether this target is reachable -- full port/service discovery is
        ``services/discovery-service``'s own concern, not this service's.
        """
        return DiscoveryResult(host=self.config.host, reachable=await self.validate())


__all__ = ["SshConnector"]
