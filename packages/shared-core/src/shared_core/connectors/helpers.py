"""Small, dependency-free utility functions shared across the SDK."""

from __future__ import annotations

from typing import Any

from shared_core.connectors.base import BaseConnector

_BYTES_PER_UNIT = 1024.0
_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(num_bytes: float) -> str:
    """Format a byte count as a compact human-readable string (e.g. ``"2.5 MB"``)."""
    size = float(num_bytes)
    for unit in _BYTE_UNITS:
        if size < _BYTES_PER_UNIT:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{size:.1f} {_BYTE_UNITS[-1]}"


def connector_summary(connector: BaseConnector) -> dict[str, Any]:
    """A JSON-serializable summary of *connector*'s current state."""
    metrics = connector.metrics()
    return {
        "provider": connector.provider_name,
        "host": connector.config.host,
        "state": connector.state.value,
        "capabilities": sorted(
            capability.value for capability in connector.describe_capabilities()
        ),
        "connection_count": metrics.connection_count,
        "success_count": metrics.success_count,
        "failure_count": metrics.failure_count,
        "retry_count": metrics.retry_count,
    }


__all__ = ["connector_summary", "format_bytes"]
