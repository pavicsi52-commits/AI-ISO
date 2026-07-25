# Enterprise Cache Framework

No service shall communicate directly with Redis -- every cache operation
goes through this package
(docs/019_Enterprise_Cache_Framework.md.txt "OBJECTIVE"). Cache Manager,
Distributed Locks, TTL Management, Cache Decorators, Query Cache, Session
Cache, Rate Limit Cache, Feature Flag Cache, Health Monitoring, Metrics,
Cache Invalidation, Redis Cluster/Sentinel support.

## Cache Philosophy

Cache improves performance. Cache never becomes the source of truth --
PostgreSQL remains the source of truth. Cache failures never corrupt
business data: every operation here is designed to fail closed (a miss, an
exception) rather than silently return stale or wrong data.

## Developer Guide

```python
from shared_core.cache import create_cache_framework, CacheSettings

framework = await create_cache_framework(CacheSettings())  # waits for Redis to be ready
await framework.manager.set("key", {"a": 1}, ttl_seconds=300)
value = await framework.manager.get("key")
health = await framework.check_health()
await framework.shutdown()
```

`create_cache_framework()` is the one call a service's startup makes: it
builds the client (standalone, Sentinel, or Cluster, per
`CacheSettings.mode`), waits (with retry/backoff) for Redis to accept
connections, and hands back a `CacheFramework` bundling the client and
`CacheManager`.

### Cache Manager

```python
from shared_core.cache import CacheManager

await manager.set(key, value, ttl_seconds=300)
value = await manager.get(key)
await manager.delete(key)
await manager.exists(key)
await manager.increment(key)              # atomic counters
await manager.expire(key, ttl_seconds)
await manager.persist(key)                # remove TTL
await manager.touch(key, ttl_seconds=60)  # sliding TTL
await manager.clear("aiios:org:*")        # pattern-based bulk delete
await manager.bulk_set({...}); await manager.bulk_get([...]); await manager.bulk_delete([...])
```

Every value passes through an automatic serialize -> compress -> encrypt
pipeline on write (and the inverse on read), configured via
`CacheSettings`: JSON/MessagePack/Pickle(internal-only) serialization,
threshold-gated Gzip/Zstandard compression, optional AES-256-GCM
encryption for sensitive values. `CacheManager.statistics` exposes
rolling hit/miss/set/delete counters.

### Cache Keys

```python
from shared_core.cache import build_cache_key, organization_key, asset_key

organization_key(str(org_id))   # "aiios:organization:<id>"
build_cache_key("custom", "part")
```

Never hardcode a cache key inline -- every domain key goes through a named
builder (or `build_cache_key` for anything not yet named) so the
`aiios:` namespace prefix and separator stay centralized.

### Cache Decorators

```python
from shared_core.cache.decorators import cached, cache_evict, invalidate, refresh, rate_limit

@cached(manager, key_prefix="asset-search", ttl_seconds=60)
async def search_assets(query: str) -> list[dict]: ...

@cache_evict(manager, key_prefix="asset-search")
async def create_asset(...) -> Asset: ...
```

Imported from `shared_core.cache.decorators` directly (not the package
root): the new `distributed_lock` decorator there shares its name with
`shared_core.cache.locks.distributed_lock` (the context manager) --
importing both into one namespace would shadow one with the other.
`cached`/`cache_evict` remain re-exported at the package root as the
Prompt 012 baseline always was.

### Distributed Locks

```python
from shared_core.cache import DistributedLock, distributed_lock, Redlock, redlock

async with distributed_lock(client, "resource-key", ttl_seconds=30):
    ...  # exclusive access, released automatically on exit

async with redlock([client_a, client_b, client_c], "resource-key"):
    ...  # quorum-based, safe against a single node's failure
```

`DistributedLock` is a single-node lock (`SET NX EX` + `WATCH`/`MULTI`/
`EXEC` release, so it can never delete a lock it no longer owns) with
`renew()` for long-running work. `Redlock` implements the actual
multi-node Redlock algorithm -- quorum acquisition across independent
Redis instances, with elapsed time and clock-drift subtracted from the
claimed validity window.

### Rate Limiting

```python
from shared_core.cache.ratelimit import RateLimitCache

limiter = RateLimitCache(manager, max_requests=100, window_seconds=60, penalty_seconds=60)
status = await limiter.check(user_id)  # RateLimitStatus(allowed, remaining, retry_after_seconds, blocked)
```

Fixed-window counting with an escalating block once the limit is
exceeded. `shared_core.security.ratelimit.DistributedRateLimiter`
(Prompt 017) is a security-specific consumer with sliding-window-log
semantics, built directly on `CacheManager`; unaffected by this module.

### Session Cache

```python
from shared_core.cache.sessions import SessionCache, RefreshTokenCache

sessions = SessionCache(manager, idle_timeout_seconds=1800)
await sessions.store(session_id, {"user_id": ..., "tenant_id": ...})
data = await sessions.get(session_id)  # sliding TTL: refreshed on access
```

Generic, data-shape-agnostic session storage -- unlike Prompt 017's
`shared_core.security.sessions.SessionManager` (which owns the specific
`Session`/`SecurityContext` shape for authentication), this stores
whatever dict a caller gives it, for any short-lived keyed state.

### Query Cache

```python
from shared_core.cache.queries import QueryCache

cache = QueryCache(manager, collection="assets", ttl_seconds=60)
await cache.set(results, search="gpu", page=1, sort="name")
cached = await cache.get(search="gpu", page=1, sort="name")
await cache.invalidate_all()  # call after any write to the collection
```

### Feature Flags

```python
from shared_core.cache.feature_flags import FeatureFlagCache, FeatureFlag, FeatureFlagScope

flags = FeatureFlagCache(manager)
await flags.set_flag(FeatureFlag(name="new_ui", enabled=True, rollout_percentage=25.0))
await flags.is_enabled("new_ui", rollout_key=str(user_id))  # deterministic per-key rollout
```

### Cache Invalidation

```python
from shared_core.cache.cleanup import DependencyTracker, EventInvalidator, invalidate_pattern

tracker = DependencyTracker(manager)
await tracker.track("asset:123", some_cache_key)   # dependency-based
await tracker.invalidate_tag("asset:123")           # invalidates everything tracked under it

invalidator = EventInvalidator()
invalidator.on("asset.updated", some_handler)        # event-driven
await invalidator.handle("asset.updated")
```

### Cache Warmup

```python
from shared_core.cache.warmup import WarmupRegistry, warmup_task

registry = WarmupRegistry()

@warmup_task(registry)
async def _warm_assets(cache: CacheManager) -> None: ...

await registry.run(manager)  # bounded concurrency; one failing task never blocks the rest
```

### Health and Metrics

```python
from shared_core.cache.health import get_health_report
from shared_core.cache import get_cluster_status, get_sentinel_status

report = await get_health_report(client, statistics=manager.statistics)
# report.status, .latency_ms, .used_memory_bytes, .key_count, .hit_ratio, .miss_ratio, .replication_role
```

Prometheus metrics (`shared_core.cache.metrics`) reuse
`shared_core.metrics.standard.cache_hits_total`/`cache_misses_total`
(already registered since Prompt 012) and add the rest docs/019 "METRICS"
requires as gauges (evictions, expired keys, memory, connections, hit
ratio, ops/sec) sourced from Redis `INFO` and `CacheStatistics`.

## Redis Cluster Guide

```python
from shared_core.cache import CacheMode, CacheSettings, ClusterNode

settings = CacheSettings(mode=CacheMode.CLUSTER, cluster_nodes=(ClusterNode(host="node-1"), ...))
client = create_client(settings)  # a RedisCluster, routing commands to the correct shard
```

## Redis Sentinel Guide

```python
from shared_core.cache import CacheMode, CacheSettings, SentinelNode

settings = CacheSettings(
    mode=CacheMode.SENTINEL,
    sentinel_nodes=(SentinelNode(host="sentinel-1"), ...),
    sentinel_master_name="mymaster",
)
client = create_client(settings)  # a client for the current Sentinel-elected master
```

Cluster/Sentinel client *construction* is fully tested; the actual
failover/topology-discovery behavior needs a real multi-node deployment
this environment's `docker-compose.yml` doesn't provide (it runs
standalone Redis) -- exercised at the "does it build and route correctly"
level, not end-to-end failover.

## Performance Guide

- **Async only** -- every operation is a coroutine; no sync fallback path.
- **Pipeline support** -- `bulk_set`/`bulk_get`/`bulk_delete` use Redis
  pipelining (`MGET`/pipelined `SET`s), not N round trips.
- **Connection pooling** -- standalone clients use a bounded
  `BlockingConnectionPool` (`pool_max_size` is a real ceiling, not advisory).
- **Compression threshold** -- values under `compression_threshold_bytes`
  (default 1024) skip compression entirely; compressing a 20-byte value
  costs more CPU than it saves in bytes.
- **Lazy serialization** -- nothing is serialized until `set()`/`bulk_set()`
  actually writes it; a cache miss never pays a serialization cost.

## Architecture Notes

- **PostgreSQL remains the source of truth.** This framework degrades
  gracefully by design -- a `CacheConnectionError` should mean "fall
  through to the origin," never "the request fails."
- **No circular imports**: this package depends on nothing in
  `shared_core.security` (a `cache -> security` import for AES-256 key
  generation was tried and reverted -- `security` already depends on
  `cache` via `security.ratelimit`/`security.sessions`, so that direction
  would have cycled). `shared_core.cache.encryption` implements its own
  two-line AES-256 key generation rather than importing
  `shared_core.security.encryption`'s, even though both use the same
  algorithm and key format.
- **`locks.py` renamed from Prompt 012's `lock.py`** to match this
  prompt's directory structure -- the only import path that changed.
- **Package renames from Prompt 012**: `client.py`/`decorators.py`/
  `keys.py`/`manager.py` stayed the same file, expanded in place.
- **Six of the seven `@cache decorator` names, plus `cached`/`cache_evict`,
  live in `shared_core.cache.decorators` and are not re-exported at the
  package root** -- see "Cache Decorators" above.
