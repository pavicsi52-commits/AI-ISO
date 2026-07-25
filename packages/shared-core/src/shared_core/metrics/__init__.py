"""Prometheus metrics: namespaced registry plus standard cross-cutting metrics."""

from shared_core.metrics.registry import (
    create_counter,
    create_gauge,
    create_histogram,
    default_registry,
)
from shared_core.metrics.standard import (
    cache_hits_total,
    cache_misses_total,
    http_request_duration_seconds,
    http_requests_total,
    queue_messages_consumed_total,
    queue_messages_dead_lettered_total,
    queue_messages_failed_total,
    queue_messages_published_total,
)

__all__ = [
    "cache_hits_total",
    "cache_misses_total",
    "create_counter",
    "create_gauge",
    "create_histogram",
    "default_registry",
    "http_request_duration_seconds",
    "http_requests_total",
    "queue_messages_consumed_total",
    "queue_messages_dead_lettered_total",
    "queue_messages_failed_total",
    "queue_messages_published_total",
]
