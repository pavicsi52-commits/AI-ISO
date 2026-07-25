"""Cache health checks.

Per docs/019_Enterprise_Cache_Framework.md.txt "HEALTH CHECKS": Redis
Connectivity, Latency, Memory Usage, Key Count, Hit Ratio, Miss Ratio,
Replication Status. ("Cluster Status"/"Sentinel Status" are covered by
:func:`shared_core.cache.cluster.get_cluster_status`/
:func:`shared_core.cache.sentinel.get_sentinel_status` -- topology-specific,
so not duplicated here.)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis

from shared_core.cache.statistics import CacheStatistics
from shared_core.enums.health_status import HealthStatus


@dataclass(frozen=True, slots=True)
class CacheHealthReport:
    """A full cache health snapshot."""

    status: HealthStatus
    latency_ms: float
    used_memory_bytes: int | None
    key_count: int | None
    hit_ratio: float | None
    miss_ratio: float | None
    replication_role: str | None


async def check_cache_health(client: Redis) -> tuple[HealthStatus, float]:
    """Check Redis connectivity and measure round-trip latency.

    Returns:
        A ``(status, latency_ms)`` tuple. Status is ``UNHEALTHY`` if the
        ``PING`` attempt raises.
    """
    start = time.perf_counter()
    try:
        await client.ping()
    except Exception:
        return HealthStatus.UNHEALTHY, round((time.perf_counter() - start) * 1000, 2)
    return HealthStatus.HEALTHY, round((time.perf_counter() - start) * 1000, 2)


async def get_health_report(
    client: Redis, *, statistics: CacheStatistics | None = None
) -> CacheHealthReport:
    """Run the full "HEALTH CHECKS" check set against *client*."""
    status, latency_ms = await check_cache_health(client)
    used_memory_bytes: int | None = None
    key_count: int | None = None
    replication_role: str | None = None
    if status is HealthStatus.HEALTHY:
        try:
            info = await client.info()
            used_memory_bytes = info.get("used_memory")
            replication_role = info.get("role")
            key_count = await client.dbsize()
        except Exception:
            pass
    return CacheHealthReport(
        status=status,
        latency_ms=latency_ms,
        used_memory_bytes=used_memory_bytes,
        key_count=key_count,
        hit_ratio=statistics.hit_ratio if statistics else None,
        miss_ratio=statistics.miss_ratio if statistics else None,
        replication_role=replication_role,
    )


__all__ = ["CacheHealthReport", "check_cache_health", "get_health_report"]
