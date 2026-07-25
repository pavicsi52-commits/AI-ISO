"""The contract every protocol scanner implements.

Per docs/037 "SUPPORTED PROTOCOLS": 25 named protocols plus "Plugin-
Based Protocols." Rather than one bespoke calling convention per
protocol, every scanner in :mod:`app.scanners` implements
:class:`ProtocolScanner` -- one async ``probe()`` method taking an
address, optional port, timeout, and resolved credential, returning a
structured :class:`ScanOutcome`. ``app/scanners/registry.py`` maps
:class:`~app.models.enums.ProtocolType` to the concrete scanner
instance; ``app/services/discovery_execution.py`` (the job runner)
never branches on protocol itself, only looks the scanner up.

**A scanner must never raise for an ordinary probe failure** (refused
connection, timeout, authentication rejected, protocol-level error) --
those map to :class:`ScanOutcome` with the matching
:class:`~app.models.enums.DiscoveryResultStatus`, since a failed probe
against one target is expected, routine data, not an application
error. Only a genuinely unexpected failure (a programming error, a
missing dependency) may propagate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import DiscoveryResultStatus, ProtocolType


@dataclass(slots=True)
class ScanCredential:
    """Resolved credential material for one probe.

    Built fresh per probe from
    ``app/discovery/credentials.py::CredentialResolver`` (which itself
    calls ``services/secrets-management-service`` live) and never
    persisted anywhere -- see that module's own docstring for why.
    """

    username: str | None = None
    password: str | None = None
    private_key: str | None = None
    token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanOutcome:
    """The structured result of one protocol probe against one target."""

    status: DiscoveryResultStatus
    latency_ms: float | None = None
    identity: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


class ProtocolScanner(ABC):
    """One protocol's real probe logic."""

    protocol: ProtocolType

    @abstractmethod
    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        """Probe *address* (optionally on *port*) using this protocol."""


__all__ = ["ProtocolScanner", "ScanCredential", "ScanOutcome"]
