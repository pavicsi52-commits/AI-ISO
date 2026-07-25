"""Rate Limit Cache.

Per docs/019_Enterprise_Cache_Framework.md.txt "RATE LIMIT CACHE": Request
Counts, Window, Penalty, Block Status. "Support distributed environments."

This is the framework-level rate-limit cache primitive: a fixed-window
counter with an escalating block ("penalty") once the limit is exceeded.
Prompt 017's :class:`shared_core.security.ratelimit.DistributedRateLimiter`
is a security-specific consumer already built directly on
:class:`~shared_core.cache.manager.CacheManager` with sliding-window-log
semantics and is unaffected by this module; new call sites that don't need
that specific algorithm should prefer this one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from shared_core.cache.constants import (
    DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    DEFAULT_RATE_LIMIT_PENALTY_SECONDS,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
)
from shared_core.cache.keys import build_cache_key
from shared_core.cache.manager import CacheManager


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    """The result of one rate-limit check."""

    allowed: bool
    remaining: int
    limit: int
    window_seconds: int
    retry_after_seconds: float | None = None
    blocked: bool = False


class RateLimitCache:
    """Fixed-window request counting with escalating block support.

    Once ``max_requests`` is exceeded within ``window_seconds``, the
    identifier is blocked for ``penalty_seconds`` regardless of the
    window resetting -- a deliberate, harsher response than "just wait
    for the window to roll over," per docs/019's "Penalty"/"Block Status".
    """

    def __init__(
        self,
        cache: CacheManager,
        *,
        max_requests: int = DEFAULT_RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        penalty_seconds: int = DEFAULT_RATE_LIMIT_PENALTY_SECONDS,
    ) -> None:
        self._cache = cache
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._penalty_seconds = penalty_seconds

    def _counter_key(self, identifier: str) -> str:
        return build_cache_key("ratelimit", "count", identifier)

    def _block_key(self, identifier: str) -> str:
        return build_cache_key("ratelimit", "block", identifier)

    async def check(self, identifier: str) -> RateLimitStatus:
        """Record one request for *identifier* and return whether it's allowed."""
        block_until: float | None = await self._cache.get(self._block_key(identifier))
        if block_until is not None:
            remaining_block = block_until - time.time()
            if remaining_block > 0:
                return RateLimitStatus(
                    allowed=False,
                    remaining=0,
                    limit=self._max_requests,
                    window_seconds=self._window_seconds,
                    retry_after_seconds=remaining_block,
                    blocked=True,
                )

        counter_key = self._counter_key(identifier)
        count = await self._cache.increment(counter_key)
        if count == 1:
            await self._cache.expire(counter_key, self._window_seconds)

        if count > self._max_requests:
            block_until_ts = time.time() + self._penalty_seconds
            await self._cache.set(
                self._block_key(identifier), block_until_ts, ttl_seconds=self._penalty_seconds
            )
            return RateLimitStatus(
                allowed=False,
                remaining=0,
                limit=self._max_requests,
                window_seconds=self._window_seconds,
                retry_after_seconds=float(self._penalty_seconds),
                blocked=True,
            )

        return RateLimitStatus(
            allowed=True,
            remaining=max(self._max_requests - count, 0),
            limit=self._max_requests,
            window_seconds=self._window_seconds,
        )

    async def is_blocked(self, identifier: str) -> bool:
        """Return whether *identifier* is currently within its penalty block."""
        block_until: float | None = await self._cache.get(self._block_key(identifier))
        return block_until is not None and block_until - time.time() > 0

    async def reset(self, identifier: str) -> None:
        """Clear an identifier's request count and any active block."""
        await self._cache.delete(self._counter_key(identifier))
        await self._cache.delete(self._block_key(identifier))


__all__ = ["RateLimitCache", "RateLimitStatus"]
