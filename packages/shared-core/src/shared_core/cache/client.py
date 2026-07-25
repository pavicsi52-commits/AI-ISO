"""Redis client creation.

:func:`create_redis_client` is the Prompt 012 baseline (a standalone client
straight from :class:`~shared_core.config.settings.RedisSettings`).
:func:`create_client` is the Prompt 019 entry point: it dispatches on
:class:`~shared_core.cache.settings.CacheSettings`'s ``mode`` to build a
standalone, Sentinel-backed, or Cluster client, so callers write topology-
agnostic code.
"""

from __future__ import annotations

from typing import cast

from redis.asyncio import Redis

from shared_core.cache.cluster import create_cluster_client
from shared_core.cache.pool import create_connection_pool
from shared_core.cache.sentinel import create_sentinel_master_client
from shared_core.cache.settings import CacheMode, CacheSettings
from shared_core.config.settings import RedisSettings


def create_redis_client(settings: RedisSettings) -> Redis:
    """Create a standalone async Redis client from settings.

    ``decode_responses=False``: :class:`~shared_core.cache.manager.CacheManager`'s
    serialize/compress/encrypt pipeline is binary-safe end to end, so the
    client must hand back raw bytes rather than having ``redis-py``
    UTF-8-decode a payload that may not be valid UTF-8 at all (compressed
    or encrypted values rarely are).
    """
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        decode_responses=False,
    )


def create_client(settings: CacheSettings) -> Redis:
    """Create the appropriate Redis client for *settings*'s configured mode.

    ``STANDALONE`` uses a bounded connection pool
    (:func:`shared_core.cache.pool.create_connection_pool`); ``SENTINEL``
    returns a client for the current Sentinel-elected master;
    ``CLUSTER`` returns a cluster-aware client that routes commands to the
    correct shard automatically.
    """
    if settings.mode is CacheMode.SENTINEL:
        return create_sentinel_master_client(settings)
    if settings.mode is CacheMode.CLUSTER:
        # RedisCluster implements the same command surface as Redis for
        # every operation this framework uses; safe to treat as one at the
        # call sites that only need get/set/expire/etc.
        return cast(Redis, create_cluster_client(settings))
    return Redis(connection_pool=create_connection_pool(settings))


__all__ = ["create_client", "create_redis_client"]
