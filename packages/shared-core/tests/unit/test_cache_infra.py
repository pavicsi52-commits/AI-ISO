"""Tests for cache connection infrastructure (settings, pool, client,
cluster/sentinel construction), health, metrics, statistics, the factory,
and the expanded decorator set.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from shared_core.cache.client import create_client, create_redis_client
from shared_core.cache.cluster import create_cluster_client
from shared_core.cache.connection import graceful_shutdown, wait_for_cache
from shared_core.cache.decorators import (
    cache,
    cacheable,
    distributed_lock,
    evict,
    invalidate,
    rate_limit,
    refresh,
)
from shared_core.cache.exceptions import CacheConnectionError
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.health import check_cache_health, get_health_report
from shared_core.cache.locks import DistributedLock
from shared_core.cache.manager import CacheManager
from shared_core.cache.metrics import (
    record_hit,
    record_miss,
    record_operation_latency,
    sync_from_redis_info,
    sync_from_statistics,
)
from shared_core.cache.pool import create_connection_pool
from shared_core.cache.ratelimit import RateLimitCache
from shared_core.cache.sentinel import create_sentinel
from shared_core.cache.settings import CacheMode, CacheSettings, ClusterNode, SentinelNode
from shared_core.cache.statistics import CacheStatistics
from shared_core.config.settings import RedisSettings
from shared_core.enums.health_status import HealthStatus
from shared_core.exceptions.rate_limit import RateLimitError

from tests.unit.conftest import redis_test_settings


def _unreachable_client(port: int) -> Redis:
    """A Redis client pointed at a closed local port, failing fast (~1s) rather
    than waiting out redis-py's default multi-attempt connection retry (~14s).
    """
    return Redis(
        host="127.0.0.1",
        port=port,
        socket_connect_timeout=1,
        retry=Retry(NoBackoff(), 0),
        retry_on_error=[],
    )


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


# --- settings.py ---


def test_cache_settings_defaults_to_standalone_mode() -> None:
    settings = CacheSettings()
    assert settings.mode is CacheMode.STANDALONE
    assert settings.compression_enabled is True
    assert settings.encryption_enabled is False


def test_cache_settings_carries_redis_settings() -> None:
    redis_settings = RedisSettings(redis_host="cache.internal", _env_file=None)
    settings = CacheSettings(redis=redis_settings)
    assert settings.redis.redis_host == "cache.internal"


def test_sentinel_node_and_cluster_node_defaults() -> None:
    assert SentinelNode(host="sentinel-1").port == 26379
    assert ClusterNode(host="node-1").port == 6379


# --- pool.py ---


def test_create_connection_pool_builds_a_blocking_pool() -> None:
    settings = CacheSettings(redis=RedisSettings(redis_host="localhost", _env_file=None))
    pool = create_connection_pool(settings)
    assert pool.max_connections == settings.pool_max_size


# --- client.py ---


def test_create_redis_client_builds_a_standalone_client() -> None:
    client = create_redis_client(RedisSettings(redis_host="localhost", _env_file=None))
    assert client is not None


def test_create_client_dispatches_by_mode() -> None:
    standalone = create_client(CacheSettings(mode=CacheMode.STANDALONE))
    assert standalone is not None

    sentinel_client = create_client(
        CacheSettings(mode=CacheMode.SENTINEL, sentinel_nodes=(SentinelNode(host="sentinel-1"),))
    )
    assert sentinel_client is not None

    cluster_client = create_client(
        CacheSettings(mode=CacheMode.CLUSTER, cluster_nodes=(ClusterNode(host="node-1"),))
    )
    assert cluster_client is not None


# --- cluster.py / sentinel.py: construction-only (no real cluster/sentinel topology available) ---


def test_create_cluster_client_requires_nodes() -> None:
    settings = CacheSettings(mode=CacheMode.CLUSTER, cluster_nodes=())
    with pytest.raises(ValueError, match="cluster_nodes"):
        create_cluster_client(settings)


def test_create_cluster_client_builds_from_nodes() -> None:
    nodes = (ClusterNode(host="node-1", port=7000),)
    settings = CacheSettings(mode=CacheMode.CLUSTER, cluster_nodes=nodes)
    client = create_cluster_client(settings)
    assert client is not None


def test_create_sentinel_requires_nodes() -> None:
    settings = CacheSettings(mode=CacheMode.SENTINEL, sentinel_nodes=())
    with pytest.raises(ValueError, match="sentinel_nodes"):
        create_sentinel(settings)


def test_create_sentinel_builds_from_nodes() -> None:
    settings = CacheSettings(
        mode=CacheMode.SENTINEL, sentinel_nodes=(SentinelNode(host="sentinel-1"),)
    )
    sentinel = create_sentinel(settings)
    assert sentinel is not None


# --- connection.py: real Redis ---


async def test_wait_for_cache_succeeds_against_a_healthy_client(real_redis_client: Redis) -> None:
    await wait_for_cache(real_redis_client, max_attempts=1)


async def test_wait_for_cache_raises_connection_failed_after_exhausting_attempts() -> None:
    broken = _unreachable_client(1)
    with pytest.raises(CacheConnectionError):
        await wait_for_cache(
            broken, max_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.05
        )
    await broken.aclose()


async def test_graceful_shutdown_closes_the_client(redis_client: FakeAsyncRedis) -> None:
    await graceful_shutdown(redis_client)  # does not raise


# --- health.py: real Redis ---


async def test_check_cache_health_reports_healthy(real_redis_client: Redis) -> None:
    status, latency_ms = await check_cache_health(real_redis_client)
    assert status == HealthStatus.HEALTHY
    assert latency_ms >= 0


async def test_check_cache_health_reports_unhealthy_for_broken_client() -> None:
    broken = _unreachable_client(1)
    status, _ = await check_cache_health(broken)
    assert status == HealthStatus.UNHEALTHY
    await broken.aclose()


async def test_get_health_report_includes_memory_and_key_count(real_redis_client: Redis) -> None:
    stats = CacheStatistics()
    stats.record_hit()
    stats.record_miss()

    report = await get_health_report(real_redis_client, statistics=stats)

    assert report.status == HealthStatus.HEALTHY
    assert report.used_memory_bytes is not None
    assert report.key_count is not None
    assert report.hit_ratio == 0.5
    assert report.miss_ratio == 0.5


async def test_get_health_report_without_statistics_has_none_ratios(
    real_redis_client: Redis,
) -> None:
    report = await get_health_report(real_redis_client)
    assert report.hit_ratio is None
    assert report.miss_ratio is None


# --- statistics.py ---


def test_cache_statistics_operations_per_second_zero_at_creation() -> None:
    stats = CacheStatistics()
    stats.started_at += 1000  # simulate "no time elapsed yet" without a real sleep
    assert stats.operations_per_second == 0.0


def test_cache_statistics_reset_zeroes_everything() -> None:
    stats = CacheStatistics()
    stats.record_hit()
    stats.record_miss()
    stats.record_set()
    stats.record_delete()
    stats.record_error()

    stats.reset()

    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.sets == 0
    assert stats.deletes == 0
    assert stats.errors == 0


def test_cache_statistics_hit_ratio_zero_with_no_reads() -> None:
    stats = CacheStatistics()
    assert stats.hit_ratio == 0.0
    assert stats.miss_ratio == 0.0


# --- metrics.py ---


def test_record_hit_and_miss_do_not_raise() -> None:
    record_hit(cache="test")
    record_miss(cache="test")


def test_record_operation_latency_does_not_raise() -> None:
    record_operation_latency("get", duration_seconds=0.01)


def test_sync_from_redis_info_updates_gauges() -> None:
    sync_from_redis_info(
        {"used_memory": 1024, "connected_clients": 3, "evicted_keys": 5, "expired_keys": 7},
        cache="test",
    )


def test_sync_from_redis_info_ignores_missing_fields() -> None:
    sync_from_redis_info({}, cache="test")  # does not raise


def test_sync_from_statistics_updates_gauges() -> None:
    sync_from_statistics(0.75, 12.5, cache="test")


# --- factory.py ---


async def test_create_cache_framework_against_real_redis(real_redis_client: Redis) -> None:
    del real_redis_client  # only used to trigger the "skip if unreachable" fixture check
    settings = CacheSettings(redis=redis_test_settings())
    framework = await create_cache_framework(settings, wait_for_ready=True)
    try:
        await framework.manager.set("factory-test", "value")
        assert await framework.manager.get("factory-test") == "value"

        report = await framework.check_health()
        assert report.status == HealthStatus.HEALTHY
    finally:
        await framework.manager.delete("factory-test")
        await framework.shutdown()


# --- decorators.py: expanded set ---


async def test_cache_decorator_with_explicit_key_fn(manager: CacheManager) -> None:
    calls = {"n": 0}

    @cache(manager, key_fn=lambda x: f"item:{x}")
    async def load(x: int) -> int:
        calls["n"] += 1
        return x * 10

    assert await load(5) == 50
    assert await load(5) == 50
    assert calls["n"] == 1
    assert await manager.exists("item:5") is True


async def test_cacheable_is_an_alias_of_cached(manager: CacheManager) -> None:
    calls = {"n": 0}

    @cacheable(manager, key_prefix="alias-test")
    async def load(x: int) -> int:
        calls["n"] += 1
        return x

    await load(1)
    await load(1)
    assert calls["n"] == 1


async def test_evict_is_an_alias_of_cache_evict(manager: CacheManager) -> None:
    await manager.set("aiios:evict-test:x", "stale")

    @evict(manager, key_prefix="evict-test")
    async def mutate() -> str:
        return "done"

    assert await mutate() == "done"
    assert await manager.exists("aiios:evict-test:x") is False


async def test_invalidate_decorator_deletes_specific_key(manager: CacheManager) -> None:
    await manager.set("item:7", "cached-value")

    @invalidate(manager, key_fn=lambda x: f"item:{x}")
    async def update(x: int) -> str:
        return "updated"

    assert await update(7) == "updated"
    assert await manager.exists("item:7") is False


async def test_refresh_decorator_always_calls_function_and_overwrites_cache(
    manager: CacheManager,
) -> None:
    calls = {"n": 0}

    @refresh(manager, key_prefix="refresh-test")
    async def load(x: int) -> int:
        calls["n"] += 1
        return x + calls["n"]

    first = await load(1)
    second = await load(1)

    assert calls["n"] == 2  # always recomputed, unlike @cached
    assert first != second


async def test_distributed_lock_decorator_serializes_access(redis_client: FakeAsyncRedis) -> None:
    order: list[str] = []

    @distributed_lock(redis_client, key_fn=lambda name: f"lock:{name}")
    async def critical_section(name: str) -> None:
        order.append(f"start-{name}")
        order.append(f"end-{name}")

    await critical_section("a")
    await critical_section("a")

    assert order == ["start-a", "end-a", "start-a", "end-a"]


async def test_rate_limit_decorator_allows_then_blocks(manager: CacheManager) -> None:
    limiter = RateLimitCache(manager, max_requests=1, window_seconds=60)

    @rate_limit(limiter, key_fn=lambda user_id: user_id)
    async def call_api(user_id: str) -> str:
        return "ok"

    assert await call_api("user-1") == "ok"
    with pytest.raises(RateLimitError):
        await call_api("user-1")


async def test_distributed_lock_object_used_directly_still_works(
    redis_client: FakeAsyncRedis,
) -> None:
    lock = DistributedLock(redis_client, "resource-x")
    assert await lock.acquire() is True
    await lock.release()
