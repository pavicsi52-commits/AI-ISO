"""Tests for the cache framework."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from shared_core.cache import (
    CacheManager,
    DistributedLock,
    LockAcquisitionFailedError,
    build_cache_key,
    cache_evict,
    cached,
    distributed_lock,
)


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def cache_manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


def test_build_cache_key_joins_with_prefix() -> None:
    assert build_cache_key("organization", "abc-123") == "aiios:organization:abc-123"


async def test_cache_manager_set_and_get_round_trip(cache_manager: CacheManager) -> None:
    await cache_manager.set("key1", {"a": 1})

    assert await cache_manager.get("key1") == {"a": 1}


async def test_cache_manager_get_returns_none_for_missing_key(
    cache_manager: CacheManager,
) -> None:
    assert await cache_manager.get("missing") is None


async def test_cache_manager_delete_removes_key(cache_manager: CacheManager) -> None:
    await cache_manager.set("key1", "value")
    await cache_manager.delete("key1")

    assert await cache_manager.exists("key1") is False


async def test_cache_manager_exists(cache_manager: CacheManager) -> None:
    assert await cache_manager.exists("key1") is False
    await cache_manager.set("key1", "value")
    assert await cache_manager.exists("key1") is True


async def test_cache_manager_expire_updates_ttl(cache_manager: CacheManager, redis_client) -> None:  # type: ignore[no-untyped-def]
    await cache_manager.set("key1", "value", ttl_seconds=1000)
    await cache_manager.expire("key1", 50)

    ttl = await redis_client.ttl("key1")
    assert 0 < ttl <= 50


async def test_cache_manager_clear_prefix_deletes_matching_keys(
    cache_manager: CacheManager,
) -> None:
    await cache_manager.set("aiios:org:1", "a")
    await cache_manager.set("aiios:org:2", "b")
    await cache_manager.set("aiios:project:1", "c")

    deleted = await cache_manager.clear_prefix("aiios:org:")

    assert deleted == 2
    assert await cache_manager.exists("aiios:org:1") is False
    assert await cache_manager.exists("aiios:project:1") is True


async def test_cache_manager_clear_prefix_returns_zero_when_no_matches(
    cache_manager: CacheManager,
) -> None:
    assert await cache_manager.clear_prefix("nothing:here:") == 0


async def test_distributed_lock_acquire_and_release(redis_client: FakeAsyncRedis) -> None:
    lock = DistributedLock(redis_client, "resource-1")

    acquired = await lock.acquire()
    assert acquired is True

    await lock.release()

    other_lock = DistributedLock(redis_client, "resource-1")
    assert await other_lock.acquire() is True


async def test_distributed_lock_blocks_concurrent_acquisition(redis_client: FakeAsyncRedis) -> None:
    lock_a = DistributedLock(redis_client, "resource-1")
    lock_b = DistributedLock(redis_client, "resource-1")

    assert await lock_a.acquire() is True
    assert await lock_b.acquire(max_retries=1, retry_delay_seconds=0.01) is False


async def test_distributed_lock_release_only_removes_own_token(
    redis_client: FakeAsyncRedis,
) -> None:
    lock_a = DistributedLock(redis_client, "resource-1")
    await lock_a.acquire()

    # A lock instance holding a different token must not be able to release it.
    imposter = DistributedLock(redis_client, "resource-1")
    await imposter.release()

    assert await redis_client.get("resource-1") is not None


async def test_distributed_lock_context_manager_releases_on_exit(
    redis_client: FakeAsyncRedis,
) -> None:
    async with distributed_lock(redis_client, "resource-1"):
        assert await redis_client.exists("resource-1")

    assert not await redis_client.exists("resource-1")


async def test_distributed_lock_context_manager_raises_when_already_held(
    redis_client: FakeAsyncRedis,
) -> None:
    await redis_client.set("resource-1", "someone-else")

    with pytest.raises(LockAcquisitionFailedError):
        async with distributed_lock(redis_client, "resource-1"):
            pass  # pragma: no cover -- should never enter


async def test_cached_decorator_only_calls_function_once_per_argument_set(
    cache_manager: CacheManager,
) -> None:
    call_count = {"n": 0}

    @cached(cache_manager, key_prefix="test")
    async def expensive(x: int) -> int:
        call_count["n"] += 1
        return x * 2

    assert await expensive(5) == 10
    assert await expensive(5) == 10
    assert call_count["n"] == 1

    assert await expensive(6) == 12
    assert call_count["n"] == 2


async def test_cache_evict_decorator_clears_prefix_after_call(cache_manager: CacheManager) -> None:
    await cache_manager.set(build_cache_key("test", "x"), "stale-value")

    @cache_evict(cache_manager, key_prefix="test")
    async def mutate() -> str:
        return "done"

    assert await mutate() == "done"
    assert await cache_manager.exists(build_cache_key("test", "x")) is False
