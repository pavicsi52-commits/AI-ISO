"""Redis Cluster client.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE CONNECTION": "Redis
Cluster". docs/019 "HEALTH CHECKS": "Cluster Status".
"""

from __future__ import annotations

from typing import Any

from redis.asyncio.cluster import ClusterNode as _RedisClusterNode
from redis.asyncio.cluster import RedisCluster

from shared_core.cache.settings import CacheSettings


def create_cluster_client(settings: CacheSettings) -> RedisCluster:
    """Create an async Redis Cluster client from *settings*.

    Raises:
        ValueError: If no cluster nodes are configured.
    """
    if not settings.cluster_nodes:
        raise ValueError("CacheSettings.cluster_nodes must be non-empty for CacheMode.CLUSTER.")
    startup_nodes = [
        _RedisClusterNode(host=node.host, port=node.port) for node in settings.cluster_nodes
    ]
    return RedisCluster(
        startup_nodes=startup_nodes,
        password=settings.redis.redis_password or None,
        socket_timeout=settings.socket_timeout_seconds,
        socket_connect_timeout=settings.socket_connect_timeout_seconds,
        ssl=settings.tls_enabled,
        decode_responses=False,
    )


async def get_cluster_status(client: RedisCluster) -> dict[str, Any]:
    """Return cluster topology info: state, known-node count, slot coverage."""
    info = await client.cluster_info()
    return {
        "state": info.get("cluster_state"),
        "known_nodes": info.get("cluster_known_nodes"),
        "size": info.get("cluster_size"),
        "slots_assigned": info.get("cluster_slots_assigned"),
    }


__all__ = ["create_cluster_client", "get_cluster_status"]
