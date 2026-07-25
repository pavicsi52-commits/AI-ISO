"""Connector SDK metrics.

Per docs/027_Enterprise_Connector_SDK.md.txt "METRICS": Connection
Count, Success Rate, Failure Rate, Latency, Retry Count, Bandwidth,
Transfer Size, Command Duration, Inventory Duration, Discovery
Duration. Reuses :mod:`shared_core.metrics.registry` directly (already
namespaced, already registered on the shared default registry) rather
than a second metrics system. Every series is labeled by ``provider``
(a connector's ``provider_name``) so metrics from different providers
sharing this one SDK don't get aggregated together.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from shared_core.metrics.registry import create_counter, create_histogram

connector_connections_total = create_counter(
    "connector_connections_total", "Total connection attempts.", labels=["provider"]
)
connector_success_total = create_counter(
    "connector_success_total", "Total operations that succeeded.", labels=["provider"]
)
connector_failure_total = create_counter(
    "connector_failure_total", "Total operations that failed.", labels=["provider"]
)
connector_retries_total = create_counter(
    "connector_retries_total", "Total retry attempts.", labels=["provider"]
)
connector_latency_seconds = create_histogram(
    "connector_latency_seconds", "Operation latency, in seconds.", labels=["provider"]
)
connector_bandwidth_bytes_total = create_counter(
    "connector_bandwidth_bytes_total",
    "Total bytes transferred.",
    labels=["provider", "direction"],
)
connector_transfer_size_bytes = create_histogram(
    "connector_transfer_size_bytes",
    "Size of a single file transfer, in bytes.",
    labels=["provider"],
)
connector_command_duration_seconds = create_histogram(
    "connector_command_duration_seconds",
    "Command execution duration, in seconds.",
    labels=["provider"],
)
connector_inventory_duration_seconds = create_histogram(
    "connector_inventory_duration_seconds",
    "Inventory collection duration, in seconds.",
    labels=["provider"],
)
connector_discovery_duration_seconds = create_histogram(
    "connector_discovery_duration_seconds", "Discovery duration, in seconds.", labels=["provider"]
)


def record_connection(provider: str) -> None:
    """Increment the connection-attempts counter ("Connection Count")."""
    connector_connections_total.labels(provider=provider).inc()


def record_success(provider: str, *, latency_seconds: float | None = None) -> None:
    """Increment the success counter, observing latency if given ("Success Rate"/"Latency")."""
    connector_success_total.labels(provider=provider).inc()
    if latency_seconds is not None:
        connector_latency_seconds.labels(provider=provider).observe(latency_seconds)


def record_failure(provider: str) -> None:
    """Increment the failure counter ("Failure Rate")."""
    connector_failure_total.labels(provider=provider).inc()


def record_retry(provider: str) -> None:
    """Increment the retry counter ("Retry Count")."""
    connector_retries_total.labels(provider=provider).inc()


def record_bandwidth(provider: str, *, direction: str, num_bytes: int) -> None:
    """Add to the bandwidth counter for *direction* (``"upload"``/``"download"``) ("Bandwidth")."""
    connector_bandwidth_bytes_total.labels(provider=provider, direction=direction).inc(num_bytes)


def record_transfer_size(provider: str, num_bytes: int) -> None:
    """Observe one file transfer's size ("Transfer Size")."""
    connector_transfer_size_bytes.labels(provider=provider).observe(num_bytes)


@contextmanager
def measure_command(provider: str) -> Iterator[None]:
    """Time a command execution ("Command Duration"), recording it regardless of outcome."""
    start = time.perf_counter()
    try:
        yield
    finally:
        connector_command_duration_seconds.labels(provider=provider).observe(
            time.perf_counter() - start
        )


@contextmanager
def measure_inventory(provider: str) -> Iterator[None]:
    """Time an inventory collection ("Inventory Duration")."""
    start = time.perf_counter()
    try:
        yield
    finally:
        connector_inventory_duration_seconds.labels(provider=provider).observe(
            time.perf_counter() - start
        )


@contextmanager
def measure_discovery(provider: str) -> Iterator[None]:
    """Time a discovery run ("Discovery Duration")."""
    start = time.perf_counter()
    try:
        yield
    finally:
        connector_discovery_duration_seconds.labels(provider=provider).observe(
            time.perf_counter() - start
        )


__all__ = [
    "connector_bandwidth_bytes_total",
    "connector_command_duration_seconds",
    "connector_connections_total",
    "connector_discovery_duration_seconds",
    "connector_failure_total",
    "connector_inventory_duration_seconds",
    "connector_latency_seconds",
    "connector_retries_total",
    "connector_success_total",
    "connector_transfer_size_bytes",
    "measure_command",
    "measure_discovery",
    "measure_inventory",
    "record_bandwidth",
    "record_connection",
    "record_failure",
    "record_retry",
    "record_success",
    "record_transfer_size",
]
