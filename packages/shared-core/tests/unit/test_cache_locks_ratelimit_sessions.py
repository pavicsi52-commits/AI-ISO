"""Tests for distributed locks (including Redlock), rate limiting, session
cache, feature flags, query cache, and cache invalidation/warmup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from shared_core.cache.cleanup import DependencyTracker, EventInvalidator, invalidate_pattern
from shared_core.cache.exceptions import LockAcquisitionFailedError
from shared_core.cache.feature_flags import FeatureFlag, FeatureFlagCache, FeatureFlagScope
from shared_core.cache.locks import DistributedLock, Redlock, redlock
from shared_core.cache.manager import CacheManager
from shared_core.cache.queries import QueryCache
from shared_core.cache.ratelimit import RateLimitCache
from shared_core.cache.sessions import RefreshTokenCache, SessionCache
from shared_core.cache.warmup import WarmupRegistry, warmup_task


def _unreachable_client(port: int) -> Redis:
    """A Redis client pointed at a closed local port, failing fast (~1s) rather
    than waiting out redis-py's default multi-attempt connection retry (~14s).
    """
    return Redis(
        host="127.0.0.1",
        port=port,
        socket_connect_timeout=1,
        socket_timeout=1,
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


# --- locks.py: DistributedLock.renew ---


async def test_distributed_lock_renew_extends_ttl_when_held(redis_client: FakeAsyncRedis) -> None:
    lock = DistributedLock(redis_client, "resource-1")
    await lock.acquire(ttl_seconds=5)

    assert await lock.renew(ttl_seconds=100) is True
    assert await redis_client.ttl("resource-1") > 5


async def test_distributed_lock_renew_fails_when_not_held(redis_client: FakeAsyncRedis) -> None:
    holder = DistributedLock(redis_client, "resource-1")
    await holder.acquire()

    imposter = DistributedLock(redis_client, "resource-1")
    assert await imposter.renew() is False


# --- locks.py: Redlock ---


async def test_redlock_acquires_with_full_quorum() -> None:
    node_a, node_b, node_c = FakeAsyncRedis(), FakeAsyncRedis(), FakeAsyncRedis()
    try:
        lock = Redlock([node_a, node_b, node_c], "resource-1")
        assert await lock.acquire(ttl_seconds=10) is True
        await lock.release()
    finally:
        await node_a.aclose()
        await node_b.aclose()
        await node_c.aclose()


async def test_redlock_acquires_with_majority_despite_one_unreachable_node() -> None:
    node_a, node_b = FakeAsyncRedis(), FakeAsyncRedis()
    unreachable = _unreachable_client(1)
    try:
        lock = Redlock([node_a, node_b, unreachable], "resource-1")
        assert await lock.acquire(ttl_seconds=10) is True
    finally:
        await node_a.aclose()
        await node_b.aclose()
        await unreachable.aclose()


async def test_redlock_fails_without_quorum() -> None:
    unreachable_a = _unreachable_client(1)
    unreachable_b = _unreachable_client(2)
    node_c = FakeAsyncRedis()
    try:
        lock = Redlock([unreachable_a, unreachable_b, node_c], "resource-1")
        assert await lock.acquire(ttl_seconds=10) is False
    finally:
        await unreachable_a.aclose()
        await unreachable_b.aclose()
        await node_c.aclose()


def test_redlock_requires_at_least_one_client() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Redlock([], "resource-1")


async def test_redlock_context_manager_releases_on_exit() -> None:
    node_a, node_b = FakeAsyncRedis(), FakeAsyncRedis()
    try:
        async with redlock([node_a, node_b], "resource-1"):
            assert await node_a.exists("resource-1")
        assert not await node_a.exists("resource-1")
    finally:
        await node_a.aclose()
        await node_b.aclose()


async def test_redlock_context_manager_raises_when_quorum_unreachable() -> None:
    unreachable_a = _unreachable_client(1)
    unreachable_b = _unreachable_client(2)
    try:
        with pytest.raises(LockAcquisitionFailedError):
            async with redlock([unreachable_a, unreachable_b], "resource-1"):
                pass  # pragma: no cover -- should never enter
    finally:
        await unreachable_a.aclose()
        await unreachable_b.aclose()


# --- ratelimit.py ---


async def test_rate_limit_cache_allows_up_to_the_limit(manager: CacheManager) -> None:
    limiter = RateLimitCache(manager, max_requests=2, window_seconds=60)

    first = await limiter.check("user-1")
    second = await limiter.check("user-1")
    third = await limiter.check("user-1")

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0
    assert third.allowed is False
    assert third.blocked is True


async def test_rate_limit_cache_blocks_further_requests_during_penalty(
    manager: CacheManager,
) -> None:
    limiter = RateLimitCache(manager, max_requests=1, window_seconds=60, penalty_seconds=60)

    await limiter.check("user-1")
    await limiter.check("user-1")  # triggers block

    assert await limiter.is_blocked("user-1") is True
    status = await limiter.check("user-1")
    assert status.allowed is False
    assert status.blocked is True


async def test_rate_limit_cache_reset_clears_count_and_block(manager: CacheManager) -> None:
    limiter = RateLimitCache(manager, max_requests=1, window_seconds=60)
    await limiter.check("user-1")
    await limiter.check("user-1")  # blocked now

    await limiter.reset("user-1")

    assert await limiter.is_blocked("user-1") is False
    status = await limiter.check("user-1")
    assert status.allowed is True


async def test_rate_limit_cache_is_blocked_false_when_never_checked(manager: CacheManager) -> None:
    limiter = RateLimitCache(manager)
    assert await limiter.is_blocked("never-seen") is False


# --- sessions.py ---


async def test_session_cache_store_and_get(manager: CacheManager) -> None:
    cache = SessionCache(manager)
    await cache.store("session-1", {"user_id": "u1", "tenant_id": "t1"})

    data = await cache.get("session-1")

    assert data == {"user_id": "u1", "tenant_id": "t1"}


async def test_session_cache_get_missing_returns_none(manager: CacheManager) -> None:
    cache = SessionCache(manager)
    assert await cache.get("missing") is None


async def test_session_cache_get_without_touch_does_not_extend(manager: CacheManager) -> None:
    cache = SessionCache(manager, idle_timeout_seconds=1000)
    await cache.store("session-1", {"a": 1})

    data = await cache.get("session-1", touch=False)

    assert data == {"a": 1}


async def test_session_cache_extend_and_revoke(manager: CacheManager) -> None:
    cache = SessionCache(manager)
    await cache.store("session-1", {"a": 1})

    assert await cache.extend("session-1", ttl_seconds=500) is True

    await cache.revoke("session-1")
    assert await cache.get("session-1") is None


async def test_refresh_token_cache_store_get_revoke(manager: CacheManager) -> None:
    cache = RefreshTokenCache(manager)
    await cache.store("token-1", {"user_id": "u1"})

    assert await cache.get("token-1") == {"user_id": "u1"}

    await cache.revoke("token-1")
    assert await cache.get("token-1") is None


# --- feature_flags.py ---


async def test_feature_flag_cache_set_and_is_enabled(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(FeatureFlag(name="new_ui", enabled=True))

    assert await flags.is_enabled("new_ui") is True


async def test_feature_flag_cache_disabled_flag_is_never_enabled(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(FeatureFlag(name="broken", enabled=False, rollout_percentage=100.0))

    assert await flags.is_enabled("broken") is False


async def test_feature_flag_cache_unset_flag_is_disabled(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    assert await flags.is_enabled("never_set") is False
    assert await flags.get_flag("never_set") is None


async def test_feature_flag_cache_zero_rollout_always_disabled(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(FeatureFlag(name="canary", enabled=True, rollout_percentage=0.0))

    assert await flags.is_enabled("canary", rollout_key="any-user") is False


async def test_feature_flag_cache_rollout_percentage_is_deterministic_per_key(
    manager: CacheManager,
) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(FeatureFlag(name="canary", enabled=True, rollout_percentage=50.0))

    first_check = await flags.is_enabled("canary", rollout_key="user-42")
    second_check = await flags.is_enabled("canary", rollout_key="user-42")

    assert first_check == second_check


async def test_feature_flag_cache_scoped_flags(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(
        FeatureFlag(name="feature_x", enabled=True, scope=FeatureFlagScope.ORGANIZATION),
        scope_id="org-1",
    )

    assert (
        await flags.is_enabled("feature_x", scope=FeatureFlagScope.ORGANIZATION, scope_id="org-1")
        is True
    )
    assert (
        await flags.is_enabled("feature_x", scope=FeatureFlagScope.ORGANIZATION, scope_id="org-2")
        is False
    )


async def test_feature_flag_cache_delete_flag(manager: CacheManager) -> None:
    flags = FeatureFlagCache(manager)
    await flags.set_flag(FeatureFlag(name="temp", enabled=True))

    await flags.delete_flag("temp")

    assert await flags.get_flag("temp") is None


# --- queries.py ---


async def test_query_cache_set_and_get(manager: CacheManager) -> None:
    cache = QueryCache(manager, collection="assets")
    await cache.set(["a", "b"], search="gpu", page=1)

    result = await cache.get(search="gpu", page=1)

    assert result == ["a", "b"]


async def test_query_cache_different_params_are_different_entries(manager: CacheManager) -> None:
    cache = QueryCache(manager, collection="assets")
    await cache.set(["a"], search="gpu", page=1)
    await cache.set(["b"], search="gpu", page=2)

    assert await cache.get(search="gpu", page=1) == ["a"]
    assert await cache.get(search="gpu", page=2) == ["b"]


async def test_query_cache_invalidate_all_clears_the_collection(manager: CacheManager) -> None:
    cache = QueryCache(manager, collection="assets")
    await cache.set(["a"], search="gpu", page=1)
    await cache.set(["b"], search="cpu", page=1)

    deleted = await cache.invalidate_all()

    assert deleted == 2
    assert await cache.get(search="gpu", page=1) is None


async def test_query_cache_get_missing_returns_none(manager: CacheManager) -> None:
    cache = QueryCache(manager, collection="assets")
    assert await cache.get(search="nothing") is None


# --- cleanup.py ---


async def test_dependency_tracker_invalidate_tag_deletes_tracked_keys(
    manager: CacheManager,
) -> None:
    tracker = DependencyTracker(manager)
    await manager.set("query:1", "result-a")
    await manager.set("query:2", "result-b")
    await tracker.track("asset:123", "query:1")
    await tracker.track("asset:123", "query:2")

    deleted = await tracker.invalidate_tag("asset:123")

    assert deleted == 2
    assert await manager.exists("query:1") is False
    assert await manager.exists("query:2") is False


async def test_dependency_tracker_track_is_idempotent(manager: CacheManager) -> None:
    tracker = DependencyTracker(manager)
    await tracker.track("tag-1", "key-1")
    await tracker.track("tag-1", "key-1")

    members = await manager.get("aiios:tag:tag-1")
    assert members == ["key-1"]


async def test_dependency_tracker_invalidate_tag_with_no_members(manager: CacheManager) -> None:
    tracker = DependencyTracker(manager)
    assert await tracker.invalidate_tag("never-tracked") == 0


async def test_invalidate_pattern(manager: CacheManager) -> None:
    await manager.set("aiios:a:1", "x")
    await manager.set("aiios:a:2", "y")

    deleted = await invalidate_pattern(manager, "aiios:a:*")

    assert deleted == 2


async def test_event_invalidator_runs_registered_handlers() -> None:
    invalidator = EventInvalidator()
    calls: list[str] = []

    async def handler_one() -> None:
        calls.append("one")

    async def handler_two() -> None:
        calls.append("two")

    invalidator.on("asset.updated", handler_one)
    invalidator.on("asset.updated", handler_two)

    ran = await invalidator.handle("asset.updated")

    assert ran == 2
    assert calls == ["one", "two"]


async def test_event_invalidator_unregistered_event_runs_nothing() -> None:
    invalidator = EventInvalidator()
    assert await invalidator.handle("unknown.event") == 0


# --- warmup.py ---


async def test_warmup_registry_runs_registered_tasks(manager: CacheManager) -> None:
    registry = WarmupRegistry()
    ran: list[str] = []

    @warmup_task(registry)
    async def _warm_assets(cache: CacheManager) -> None:
        await cache.set("warm:assets", "loaded")
        ran.append("assets")

    @warmup_task(registry)
    async def _warm_users(cache: CacheManager) -> None:
        await cache.set("warm:users", "loaded")
        ran.append("users")

    count = await registry.run(manager)

    assert count == 2
    assert set(ran) == {"assets", "users"}
    assert await manager.get("warm:assets") == "loaded"


async def test_warmup_registry_continues_after_a_task_fails(manager: CacheManager) -> None:
    registry = WarmupRegistry()

    @warmup_task(registry)
    async def _failing(cache: CacheManager) -> None:
        raise RuntimeError("boom")

    @warmup_task(registry)
    async def _succeeding(cache: CacheManager) -> None:
        await cache.set("warm:ok", "loaded")

    await registry.run(manager)

    assert await manager.get("warm:ok") == "loaded"
