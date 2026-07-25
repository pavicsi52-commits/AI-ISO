"""Prometheus cache metrics.

Per docs/019_Enterprise_Cache_Framework.md.txt "METRICS": Cache Hits,
Cache Misses, Hit Ratio, Miss Ratio, Latency, Evictions, Expired Keys,
Memory Usage, Connections, Operations Per Second. "Expose Prometheus
metrics."

Reuses :data:`shared_core.metrics.standard.cache_hits_total`/
``cache_misses_total`` (already registered there since Prompt 012) rather
than defining duplicate same-named Prometheus series; adds the metrics
this prompt requires that the Prompt 012 baseline didn't cover. The
Redis-``INFO``-sourced values (evictions, expired keys, memory, clients)
are exposed as gauges, not counters -- they mirror an already-cumulative
value Redis itself maintains, so ``.set()`` (not ``.inc()``) is the
correct operation.
"""

from __future__ import annotations

from typing import Any

from shared_core.metrics.registry import create_gauge, create_histogram
from shared_core.metrics.standard import cache_hits_total, cache_misses_total

cache_operation_latency_seconds = create_histogram(
    "cache_operation_latency_seconds",
    "Cache operation latency, in seconds.",
    labels=["operation"],
)
cache_evicted_keys = create_gauge(
    "cache_evicted_keys", "Total keys evicted by Redis's maxmemory policy.", labels=["cache"]
)
cache_expired_keys = create_gauge(
    "cache_expired_keys", "Total keys that expired via TTL.", labels=["cache"]
)
cache_memory_usage_bytes = create_gauge(
    "cache_memory_usage_bytes", "Redis used_memory, in bytes.", labels=["cache"]
)
cache_connected_clients = create_gauge(
    "cache_connected_clients", "Number of client connections to Redis.", labels=["cache"]
)
cache_hit_ratio = create_gauge(
    "cache_hit_ratio", "Rolling cache hit ratio, in [0, 1].", labels=["cache"]
)
cache_operations_per_second = create_gauge(
    "cache_operations_per_second", "Rolling average cache operations per second.", labels=["cache"]
)


def record_hit(*, cache: str = "default") -> None:
    """Record one cache read that found a value."""
    cache_hits_total.labels(cache=cache).inc()


def record_miss(*, cache: str = "default") -> None:
    """Record one cache read that found nothing."""
    cache_misses_total.labels(cache=cache).inc()


def record_operation_latency(operation: str, *, duration_seconds: float) -> None:
    """Record how long one cache operation took."""
    cache_operation_latency_seconds.labels(operation=operation).observe(duration_seconds)


def sync_from_redis_info(info: dict[str, Any], *, cache: str = "default") -> None:
    """Update the gauges sourced from a Redis ``INFO`` reply, not per-operation instrumentation."""
    if "used_memory" in info:
        cache_memory_usage_bytes.labels(cache=cache).set(info["used_memory"])
    if "connected_clients" in info:
        cache_connected_clients.labels(cache=cache).set(info["connected_clients"])
    if "evicted_keys" in info:
        cache_evicted_keys.labels(cache=cache).set(info["evicted_keys"])
    if "expired_keys" in info:
        cache_expired_keys.labels(cache=cache).set(info["expired_keys"])


def sync_from_statistics(
    hit_ratio: float, operations_per_second: float, *, cache: str = "default"
) -> None:
    """Update the gauges sourced from a :class:`~shared_core.cache.statistics.CacheStatistics`."""
    cache_hit_ratio.labels(cache=cache).set(hit_ratio)
    cache_operations_per_second.labels(cache=cache).set(operations_per_second)


__all__ = [
    "cache_connected_clients",
    "cache_evicted_keys",
    "cache_expired_keys",
    "cache_hit_ratio",
    "cache_memory_usage_bytes",
    "cache_operation_latency_seconds",
    "cache_operations_per_second",
    "record_hit",
    "record_miss",
    "record_operation_latency",
    "sync_from_redis_info",
    "sync_from_statistics",
]
