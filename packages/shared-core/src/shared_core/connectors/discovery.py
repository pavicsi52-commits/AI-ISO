"""Discovery primitives.

Per docs/027_Enterprise_Connector_SDK.md.txt "DISCOVERY": Host
Discovery, Service Discovery, Port Discovery, Resource Discovery,
Capability Discovery, Plugin Discovery. Reuses
:func:`shared_core.monitoring.checks.check_tcp_reachable` (Prompt 023,
already a generic TCP-reachability primitive) for host/port discovery
rather than reimplementing socket probing a second time. "Resource
Discovery"/"Capability Discovery" are entirely protocol-specific (what
a target actually has to discover depends on which provider is asking)
-- this module only defines the shared result shape every provider's
``discover()`` returns, plus the one discovery primitive that's
genuinely protocol-agnostic: whether a port is open.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from shared_core.connectors.constants import DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import check_tcp_reachable


@dataclass(frozen=True, slots=True)
class DiscoveredPort:
    """One port's discovery result ("Port Discovery")."""

    port: int
    open: bool
    latency_ms: float


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """What one ``BaseConnector.discover()`` call found."""

    host: str
    reachable: bool
    ports: tuple[DiscoveredPort, ...] = ()
    services: tuple[str, ...] = ()
    resources: dict[str, Any] = field(default_factory=dict)
    capabilities: frozenset[str] = frozenset()


async def discover_ports(
    host: str,
    ports: Iterable[int],
    *,
    timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS,
) -> tuple[DiscoveredPort, ...]:
    """Probe every port in *ports* on *host* concurrently ("Port Discovery")."""
    port_list = list(ports)
    checks = await asyncio.gather(
        *(
            check_tcp_reachable(str(port), host, port, timeout_seconds=timeout_seconds)
            for port in port_list
        )
    )
    return tuple(
        DiscoveredPort(
            port=port, open=check.status == HealthStatus.HEALTHY, latency_ms=check.latency_ms
        )
        for port, check in zip(port_list, checks, strict=True)
    )


async def discover_host(
    host: str,
    *,
    ports: Iterable[int] = (),
    timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS,
) -> DiscoveryResult:
    """Discover whether *host* is reachable, and which of *ports* are open ("Host Discovery")."""
    discovered_ports = await discover_ports(host, ports, timeout_seconds=timeout_seconds)
    reachable = any(port.open for port in discovered_ports) if discovered_ports else False
    return DiscoveryResult(host=host, reachable=reachable, ports=discovered_ports)


__all__ = ["DiscoveredPort", "DiscoveryResult", "discover_host", "discover_ports"]
