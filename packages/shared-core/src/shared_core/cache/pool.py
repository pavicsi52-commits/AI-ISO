"""Redis connection pooling.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE CONNECTION":
"Connection Pool". Only standalone connections use an explicit pool here --
Sentinel and Cluster clients (:mod:`shared_core.cache.sentinel`,
:mod:`shared_core.cache.cluster`) manage their own per-node pools
internally via ``redis-py``.
"""

from __future__ import annotations

from redis.asyncio import BlockingConnectionPool
from redis.asyncio.connection import Connection, SSLConnection

from shared_core.cache.settings import CacheSettings


def create_connection_pool(settings: CacheSettings) -> BlockingConnectionPool:
    """Build a bounded, blocking connection pool for a standalone Redis client.

    A ``BlockingConnectionPool`` (rather than the default unbounded pool)
    makes ``pool_max_size`` a real ceiling: once exhausted, a caller waits
    for a connection to free up instead of the pool growing without bound
    under load. TLS uses a dedicated connection class
    (``redis-py``'s plain ``Connection`` doesn't accept an ``ssl`` keyword
    at all -- it's ``SSLConnection`` or nothing).
    """
    connection_class = SSLConnection if settings.tls_enabled else Connection
    return BlockingConnectionPool(
        connection_class=connection_class,
        host=settings.redis.redis_host,
        port=settings.redis.redis_port,
        db=settings.redis.redis_db,
        password=settings.redis.redis_password or None,
        max_connections=settings.pool_max_size,
        timeout=settings.socket_timeout_seconds,
        socket_timeout=settings.socket_timeout_seconds,
        socket_connect_timeout=settings.socket_connect_timeout_seconds,
        decode_responses=False,
    )


__all__ = ["create_connection_pool"]
