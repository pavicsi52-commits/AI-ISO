"""Enterprise Cache Framework.

No service shall communicate directly with Redis -- every cache operation
goes through this package (docs/019_Enterprise_Cache_Framework.md.txt
"OBJECTIVE"). Cache Manager, Distributed Locks, TTL Management, Cache
Decorators, Query Cache, Session Cache, Rate Limit Cache, Feature Flag
Cache, Health Monitoring, Metrics, Cache Invalidation, Redis
Cluster/Sentinel support.

Cache decorators (``@cache``/``@cacheable``/``@evict``/``@invalidate``/
``@refresh``/``@distributed_lock``/``@rate_limit``) are imported from
:mod:`shared_core.cache.decorators` directly, except the two Prompt 012
baseline names (``cached``, ``cache_evict``) already re-exported here --
the new decorator named ``distributed_lock`` would otherwise shadow this
package's own :func:`shared_core.cache.locks.distributed_lock` context
manager if both were imported into this namespace.
"""

from shared_core.cache.client import create_client, create_redis_client
from shared_core.cache.cluster import create_cluster_client, get_cluster_status
from shared_core.cache.compression import CompressionAlgorithm, compress, decompress
from shared_core.cache.connection import graceful_shutdown, wait_for_cache
from shared_core.cache.decorators import cache_evict, cached
from shared_core.cache.exceptions import (
    CacheConnectionError,
    CacheEncryptionError,
    CacheTimeoutError,
    CacheTTLError,
    ClusterUnavailableError,
    CompressionFailedError,
    InvalidCacheKeyError,
    LockAcquisitionFailedError,
    SerializationFailedError,
)
from shared_core.cache.factory import CacheFramework, create_cache_framework
from shared_core.cache.feature_flags import FeatureFlag, FeatureFlagCache, FeatureFlagScope
from shared_core.cache.health import CacheHealthReport, check_cache_health, get_health_report
from shared_core.cache.keys import (
    asset_key,
    build_cache_key,
    build_pattern,
    execution_key,
    inventory_key,
    job_key,
    organization_key,
    playbook_key,
    project_key,
    user_key,
    validate_cache_key,
    validation_key,
    workflow_key,
)
from shared_core.cache.locks import DistributedLock, Redlock, distributed_lock, redlock
from shared_core.cache.manager import CacheManager
from shared_core.cache.pool import create_connection_pool
from shared_core.cache.queries import QueryCache
from shared_core.cache.ratelimit import RateLimitCache, RateLimitStatus
from shared_core.cache.sentinel import (
    create_sentinel,
    create_sentinel_master_client,
    create_sentinel_replica_client,
    get_sentinel_status,
)
from shared_core.cache.sessions import RefreshTokenCache, SessionCache
from shared_core.cache.settings import (
    CacheMode,
    CacheSettings,
    ClusterNode,
    SentinelNode,
    SerializationFormat,
)
from shared_core.cache.statistics import CacheStatistics
from shared_core.cache.ttl import NO_EXPIRATION, TTLPolicy, resolve_ttl, validate_ttl

__all__ = [
    "NO_EXPIRATION",
    "CacheConnectionError",
    "CacheEncryptionError",
    "CacheFramework",
    "CacheHealthReport",
    "CacheManager",
    "CacheMode",
    "CacheSettings",
    "CacheStatistics",
    "CacheTTLError",
    "CacheTimeoutError",
    "ClusterNode",
    "ClusterUnavailableError",
    "CompressionAlgorithm",
    "CompressionFailedError",
    "DistributedLock",
    "FeatureFlag",
    "FeatureFlagCache",
    "FeatureFlagScope",
    "InvalidCacheKeyError",
    "LockAcquisitionFailedError",
    "QueryCache",
    "RateLimitCache",
    "RateLimitStatus",
    "Redlock",
    "RefreshTokenCache",
    "SentinelNode",
    "SerializationFailedError",
    "SerializationFormat",
    "SessionCache",
    "TTLPolicy",
    "asset_key",
    "build_cache_key",
    "build_pattern",
    "cache_evict",
    "cached",
    "check_cache_health",
    "compress",
    "create_cache_framework",
    "create_client",
    "create_cluster_client",
    "create_connection_pool",
    "create_redis_client",
    "create_sentinel",
    "create_sentinel_master_client",
    "create_sentinel_replica_client",
    "decompress",
    "distributed_lock",
    "execution_key",
    "get_cluster_status",
    "get_health_report",
    "get_sentinel_status",
    "graceful_shutdown",
    "inventory_key",
    "job_key",
    "organization_key",
    "playbook_key",
    "project_key",
    "redlock",
    "resolve_ttl",
    "user_key",
    "validate_cache_key",
    "validate_ttl",
    "validation_key",
    "wait_for_cache",
    "workflow_key",
]
