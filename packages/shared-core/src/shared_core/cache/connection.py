"""Connection lifecycle: retry-on-startup, graceful shutdown.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE CONNECTION":
"Retry", "Automatic Reconnect", "Health Validation". Automatic reconnect
for individual dropped connections is handled transparently by
``redis-py``'s own retry-on-timeout/health-check machinery; this module
handles the whole-cache-unavailable case at service startup and shutdown.
"""

from __future__ import annotations

import asyncio
import random

from redis.asyncio import Redis
from redis.exceptions import RedisError

from shared_core.cache.constants import (
    DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
    DEFAULT_CONNECT_MAX_ATTEMPTS,
)
from shared_core.cache.exceptions import CacheConnectionError
from shared_core.logging import get_logger

logger = get_logger("shared_core.cache.connection")


async def wait_for_cache(
    client: Redis,
    *,
    max_attempts: int = DEFAULT_CONNECT_MAX_ATTEMPTS,
    backoff_base_seconds: float = DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    backoff_max_seconds: float = DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
) -> None:
    """Block until *client* can serve a ``PING``, retrying with backoff.

    Intended for service startup, where the cache container may still be
    initializing. Raises :class:`CacheConnectionError` once *max_attempts*
    is exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await client.ping()
            return
        except RedisError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = min(backoff_base_seconds * (2 ** (attempt - 1)), backoff_max_seconds)
            delay += random.uniform(0, backoff_base_seconds)
            logger.warning(
                "cache connection attempt failed, retrying",
                extra={"attempt": attempt, "max_attempts": max_attempts, "delay_seconds": delay},
            )
            await asyncio.sleep(delay)

    raise CacheConnectionError(
        f"Could not connect to the cache after {max_attempts} attempts."
    ) from last_error


async def graceful_shutdown(client: Redis) -> None:
    """Close *client*'s connection pool. Call once at service shutdown.

    Forces ``close_connection_pool=True``: a client built from an
    explicitly-supplied pool (:func:`shared_core.cache.client.create_client`
    always builds one via :func:`shared_core.cache.pool.create_connection_pool`)
    defaults ``auto_close_connection_pool`` to ``False`` on the assumption
    the caller might reuse that pool elsewhere -- not true here, so a plain
    ``aclose()`` would silently leak every pooled connection.
    """
    logger.info("closing cache client connection pool")
    await client.aclose(close_connection_pool=True)


__all__ = ["graceful_shutdown", "wait_for_cache"]
