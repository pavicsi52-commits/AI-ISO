"""Rate limiting and quota checks.

Thin adapter onto two existing `shared_core` primitives, per this
prompt's own research phase: `shared_core.cache.ratelimit
.RateLimitCache` (a fixed-window counter with an escalating penalty
block) backs ``FIXED_WINDOW``/``TOKEN_BUCKET`` policies (its own
refuse-once-exhausted behaviour is the closest existing match to a
bucket, and no true token-bucket-with-refill primitive exists anywhere
in `shared_core`), and `shared_core.security.ratelimit
.DistributedRateLimiter` (a genuine sliding-window log) backs
``SLIDING_WINDOW`` policies directly -- not a third reimplementation of
either.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from shared_core.cache.manager import CacheManager
from shared_core.cache.ratelimit import RateLimitCache
from shared_core.security.ratelimit import DistributedRateLimiter

from app.models.enums import QuotaPeriod, RateLimitAlgorithm, RateLimitScope

RateLimiter = RateLimitCache | DistributedRateLimiter


def build_identifier(scope: RateLimitScope, reference: str | None) -> str:
    """The cache key identifying one rate-limited subject."""
    return f"{scope.value}:{reference or 'global'}"


def build_rate_limiter(
    cache_manager: CacheManager,
    *,
    algorithm: RateLimitAlgorithm,
    max_requests: int,
    window_seconds: int,
) -> RateLimiter:
    """Build the concrete limiter object for one policy's own algorithm."""
    if algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
        return DistributedRateLimiter(
            cache_manager, max_requests=max_requests, window_seconds=float(window_seconds)
        )
    return RateLimitCache(cache_manager, max_requests=max_requests, window_seconds=window_seconds)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The outcome of one rate-limit check, unified across both underlying limiter shapes."""

    allowed: bool
    remaining: int
    retry_after_seconds: float | None = None


async def check_rate_limit(limiter: RateLimiter, identifier: str) -> RateLimitDecision:
    """Check *identifier* against *limiter*, regardless of its underlying algorithm."""
    if isinstance(limiter, DistributedRateLimiter):
        allowed = await limiter.allow(identifier)
        remaining = await limiter.remaining(identifier)
        return RateLimitDecision(allowed=allowed, remaining=remaining)
    status = await limiter.check(identifier)
    return RateLimitDecision(
        allowed=status.allowed,
        remaining=status.remaining,
        retry_after_seconds=status.retry_after_seconds,
    )


def quota_period_bounds(period: QuotaPeriod, now: datetime) -> tuple[datetime, datetime]:
    """The ``[start, end)`` boundary of the quota period containing *now*."""
    if period == QuotaPeriod.DAILY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def is_quota_exceeded(*, used_value: float, limit_value: float) -> bool:
    """Whether a quota's own usage has reached or passed its limit."""
    return used_value >= limit_value


def is_period_expired(period_resets_at: datetime, *, now: datetime | None = None) -> bool:
    """Whether a quota's own tracked period has ended and needs resetting."""
    return (now or datetime.now(UTC)) >= period_resets_at


__all__ = [
    "RateLimitDecision",
    "RateLimiter",
    "build_identifier",
    "build_rate_limiter",
    "check_rate_limit",
    "is_period_expired",
    "is_quota_exceeded",
    "quota_period_bounds",
]
