"""Cache Framework factory.

Assembles the client, manager, and health/shutdown into one object a
service builds exactly once at startup -- the same "factory wires settings
into ready-to-use primitives" role
:mod:`shared_core.config.loader`/:mod:`shared_core.database.factory` play
for their own frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from shared_core.cache.client import create_client
from shared_core.cache.connection import graceful_shutdown, wait_for_cache
from shared_core.cache.health import CacheHealthReport, get_health_report
from shared_core.cache.manager import CacheManager
from shared_core.cache.settings import CacheSettings
from shared_core.cache.statistics import CacheStatistics


@dataclass(slots=True)
class CacheFramework:
    """Everything a service needs to talk to the cache, assembled once at startup."""

    client: Redis
    manager: CacheManager

    async def check_health(self) -> CacheHealthReport:
        """Run the framework's standard health check against this client."""
        return await get_health_report(self.client, statistics=self.manager.statistics)

    async def shutdown(self) -> None:
        """Gracefully close the connection pool. Call once at service shutdown."""
        await graceful_shutdown(self.client)


async def create_cache_framework(
    settings: CacheSettings, *, wait_for_ready: bool = True
) -> CacheFramework:
    """Build a :class:`CacheFramework` from Cache Framework settings.

    If *wait_for_ready* (the default), blocks with retry/backoff until the
    cache accepts connections before returning -- call this at service
    startup so the very first request doesn't race a still-initializing
    cache container.
    """
    client = create_client(settings)
    if wait_for_ready:
        await wait_for_cache(client)
    manager = CacheManager(client, settings=settings, statistics=CacheStatistics())
    return CacheFramework(client=client, manager=manager)


__all__ = ["CacheFramework", "create_cache_framework"]
