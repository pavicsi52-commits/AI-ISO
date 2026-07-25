"""Distributed rate limiting, backed by Redis via :class:`shared_core.cache.manager.CacheManager`.

Per docs/017_Enterprise_Security_Framework.md.txt "RATE LIMITING": Per
User, Per API Key, Per Organization, Per IP, Sliding Window, Burst
Control, Distributed Redis Backend. The in-process
:class:`shared_core.middleware.rate_limit.InMemoryRateLimiter` (Prompt
012) is still correct for single-replica deployments; this is for
multi-replica deployments where limits must be shared across processes.
"""

from __future__ import annotations

import time

from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager


def rate_limit_key(*, scope: str, identifier: str) -> str:
    """Build a scoped rate-limit key.

    Example: ``rate_limit_key(scope="user", identifier=str(user_id))``.
    """
    return f"{scope}:{identifier}"


class DistributedRateLimiter:
    """Sliding-window rate limiter shared across every process via Redis."""

    def __init__(self, cache: CacheManager, *, max_requests: int, window_seconds: float) -> None:
        self._cache = cache
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def allow(self, key: str) -> bool:
        """Return whether a request identified by *key* is within limits.

        Reads the current hit timestamps for *key*, drops any outside the
        sliding window, and -- only if still under the limit -- records
        this hit. Because this isn't atomic (a read-then-write across two
        Redis calls), under heavy concurrent load from the *same* key it
        can allow a small number of extra requests through a race; that's
        an accepted tradeoff for staying on the existing
        :class:`CacheManager` primitives rather than a Lua script (see
        AI_MEMORY.md's ``DistributedLock`` note on why Lua scripting is
        avoided in this environment).
        """
        cache_key = build_cache_key("ratelimit", key)
        now = time.time()
        window_start = now - self._window_seconds

        hits: list[float] = await self._cache.get(cache_key) or []
        hits = [hit for hit in hits if hit >= window_start]

        if len(hits) >= self._max_requests:
            await self._cache.set(cache_key, hits, ttl_seconds=int(self._window_seconds) + 1)
            return False

        hits.append(now)
        await self._cache.set(cache_key, hits, ttl_seconds=int(self._window_seconds) + 1)
        return True

    async def remaining(self, key: str) -> int:
        """Return how many more requests *key* may make in the current window."""
        cache_key = build_cache_key("ratelimit", key)
        window_start = time.time() - self._window_seconds
        hits: list[float] = await self._cache.get(cache_key) or []
        active_hits = [hit for hit in hits if hit >= window_start]
        return max(self._max_requests - len(active_hits), 0)
