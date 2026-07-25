"""Redis Sentinel client.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE CONNECTION": "Redis
Sentinel". docs/019 "HEALTH CHECKS": "Sentinel Status".
"""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.asyncio.sentinel import Sentinel

from shared_core.cache.settings import CacheSettings


def create_sentinel(settings: CacheSettings) -> Sentinel:
    """Create a Sentinel client from *settings*.

    Raises:
        ValueError: If no sentinel nodes are configured.
    """
    if not settings.sentinel_nodes:
        raise ValueError("CacheSettings.sentinel_nodes must be non-empty for CacheMode.SENTINEL.")
    return Sentinel(  # type: ignore[no-untyped-call]  # redis-py's Sentinel.__init__ has no stub
        [(node.host, node.port) for node in settings.sentinel_nodes],
        socket_timeout=settings.socket_timeout_seconds,
        password=settings.redis.redis_password or None,
        ssl=settings.tls_enabled,
        decode_responses=False,
    )


def create_sentinel_master_client(settings: CacheSettings) -> Redis:
    """Return a client for the Sentinel-elected master (read/write)."""
    sentinel = create_sentinel(settings)
    return sentinel.master_for(  # type: ignore[no-any-return]  # untyped stub, returns Redis at runtime
        settings.sentinel_master_name,
        password=settings.redis.redis_password or None,
        db=settings.redis.redis_db,
    )


def create_sentinel_replica_client(settings: CacheSettings) -> Redis:
    """Return a client for a Sentinel-known replica (read-only)."""
    sentinel = create_sentinel(settings)
    return sentinel.slave_for(  # type: ignore[no-any-return]  # untyped stub, returns Redis at runtime
        settings.sentinel_master_name,
        password=settings.redis.redis_password or None,
        db=settings.redis.redis_db,
    )


async def get_sentinel_status(sentinel: Sentinel, *, master_name: str) -> dict[str, Any]:
    """Return Sentinel-observed state of the named master: address, replica/sentinel counts."""
    # redis-py's stub for this async method mismatches a sync protocol overload.
    master_info = await sentinel.sentinel_master(master_name)  # type: ignore[misc]
    return {
        "ip": master_info.get("ip"),
        "port": master_info.get("port"),
        "is_master": master_info.get("is_master", True),
        "num_slaves": master_info.get("num-slaves", 0),
        "num_other_sentinels": master_info.get("num-other-sentinels", 0),
        "quorum": master_info.get("quorum"),
    }


__all__ = [
    "create_sentinel",
    "create_sentinel_master_client",
    "create_sentinel_replica_client",
    "get_sentinel_status",
]
