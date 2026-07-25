"""Connection configuration and state.

Per docs/027_Enterprise_Connector_SDK.md.txt "CONNECTION MANAGEMENT":
Timeouts, Reconnect, Keep Alive, TLS, Certificate Validation,
Compression. ("Connection Pooling", "Persistent Sessions", "Session
Reuse" are :mod:`~shared_core.connectors.pool`/
:mod:`~shared_core.connectors.session`'s own concern.)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_core.connectors.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_KEEPALIVE_INTERVAL_SECONDS,
)


class ConnectionState(StrEnum):
    """A connector's lifecycle state, per docs/027 "CONNECTOR LIFECYCLE"."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    """How to reach and secure a connection to one target."""

    host: str
    port: int | None = None
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    use_tls: bool = False
    verify_certificates: bool = True
    keep_alive: bool = True
    keepalive_interval_seconds: float = DEFAULT_KEEPALIVE_INTERVAL_SECONDS
    compression: bool = False


__all__ = ["ConnectionConfig", "ConnectionState"]
