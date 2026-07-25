"""Base connector.

Per docs/027_Enterprise_Connector_SDK.md.txt "BASE CONNECTOR": Connect,
Disconnect, Reconnect, Validate, Execute, Health, Metrics, Inventory,
Discovery, Capabilities. Per "CONNECTOR LIFECYCLE": Register,
Initialize, Authenticate, Connect, Validate, Execute, Collect,
Disconnect, Cleanup. Every concrete provider connector (SSH, WinRM,
Redfish, ...) subclasses :class:`BaseConnector` and implements its
abstract methods; this class owns the state machine, session
bookkeeping, and the default ``reconnect()``/``capabilities()``/
``metrics()`` behavior every provider shares, so no provider
reimplements them ("SDK PRINCIPLES": "Every connector inherits
BaseConnector", "Every connector follows the same lifecycle").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import Credential
from shared_core.connectors.discovery import DiscoveryResult
from shared_core.connectors.health import ConnectorHealthReport
from shared_core.connectors.inventory import InventoryReport
from shared_core.connectors.session import Session


class ConnectorCapability(StrEnum):
    """What kinds of operations a connector supports ("Capabilities")."""

    EXECUTE = "execute"
    FILE_TRANSFER = "file_transfer"
    DISCOVERY = "discovery"
    INVENTORY = "inventory"
    STREAMING = "streaming"
    BATCH = "batch"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one :meth:`BaseConnector.execute` call ("Execute")."""

    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Whether the command exited with status 0."""
        return self.exit_code == 0


@dataclass(slots=True)
class ConnectorMetricsSnapshot:
    """One connector instance's own running counters ("Metrics")."""

    connection_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    last_latency_ms: float | None = None


class BaseConnector(ABC):
    """Every provider connector's common contract and lifecycle."""

    provider_name: ClassVar[str] = "base"
    capabilities: ClassVar[frozenset[ConnectorCapability]] = frozenset()

    def __init__(self, config: ConnectionConfig, credential: Credential) -> None:
        self.config = config
        self.credential = credential
        self.state = ConnectionState.DISCONNECTED
        self.session: Session | None = None
        self._metrics = ConnectorMetricsSnapshot()

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection and authenticate ("Connect"/"Authenticate")."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection and clean up ("Disconnect"/"Cleanup")."""

    async def reconnect(self) -> None:
        """Disconnect (if connected) and connect again ("Reconnect")."""
        if self.state != ConnectionState.DISCONNECTED:
            await self.disconnect()
        self.state = ConnectionState.RECONNECTING
        await self.connect()

    @abstractmethod
    async def validate(self) -> bool:
        """Validate the current connection is usable ("Validate")."""

    @abstractmethod
    async def execute(self, command: str, **kwargs: Any) -> CommandResult:
        """Execute a command against the target ("Execute")."""

    @abstractmethod
    async def health(self) -> ConnectorHealthReport:
        """Report this connector's current health ("Health")."""

    @abstractmethod
    async def collect_inventory(self) -> InventoryReport:
        """Collect inventory from the target ("Collect"/"Inventory")."""

    @abstractmethod
    async def discover(self) -> DiscoveryResult:
        """Discover hosts/services/ports/resources this target exposes ("Discovery")."""

    def metrics(self) -> ConnectorMetricsSnapshot:
        """This connector instance's own running counters ("Metrics")."""
        return self._metrics

    def describe_capabilities(self) -> frozenset[ConnectorCapability]:
        """This connector's declared capabilities ("Capabilities")."""
        return self.capabilities

    def supports(self, capability: ConnectorCapability) -> bool:
        """Whether this connector declares *capability*."""
        return capability in self.capabilities

    def record_success(self, *, latency_ms: float | None = None) -> None:
        """Record a successful operation on this connector's own metrics snapshot."""
        self._metrics.success_count += 1
        if latency_ms is not None:
            self._metrics.last_latency_ms = latency_ms

    def record_failure(self) -> None:
        """Record a failed operation on this connector's own metrics snapshot."""
        self._metrics.failure_count += 1

    def record_retry(self) -> None:
        """Record a retry attempt on this connector's own metrics snapshot."""
        self._metrics.retry_count += 1

    def record_connection(self) -> None:
        """Record a new connection attempt on this connector's own metrics snapshot."""
        self._metrics.connection_count += 1


__all__ = ["BaseConnector", "CommandResult", "ConnectorCapability", "ConnectorMetricsSnapshot"]
