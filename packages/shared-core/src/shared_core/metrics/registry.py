"""Prometheus metrics registry.

Every AI-IOS service registers its metrics through this module so metric
names are consistently namespaced (``aiios_...``) rather than invented
ad hoc per service.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from shared_core.constants.monitoring import MonitoringConstants

default_registry = CollectorRegistry()


def create_counter(name: str, description: str, *, labels: list[str] | None = None) -> Counter:
    """Create a namespaced counter registered on the default registry."""
    return Counter(
        name,
        description,
        labelnames=labels or [],
        namespace=MonitoringConstants.METRICS_NAMESPACE,
        registry=default_registry,
    )


def create_gauge(name: str, description: str, *, labels: list[str] | None = None) -> Gauge:
    """Create a namespaced gauge registered on the default registry."""
    return Gauge(
        name,
        description,
        labelnames=labels or [],
        namespace=MonitoringConstants.METRICS_NAMESPACE,
        registry=default_registry,
    )


def create_histogram(
    name: str,
    description: str,
    *,
    labels: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> Histogram:
    """Create a namespaced histogram registered on the default registry."""
    if buckets is not None:
        return Histogram(
            name,
            description,
            labelnames=labels or [],
            namespace=MonitoringConstants.METRICS_NAMESPACE,
            registry=default_registry,
            buckets=buckets,
        )
    return Histogram(
        name,
        description,
        labelnames=labels or [],
        namespace=MonitoringConstants.METRICS_NAMESPACE,
        registry=default_registry,
    )
