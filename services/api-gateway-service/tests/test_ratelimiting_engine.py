"""Tests for app/ratelimiting/engine.py.

`build_rate_limiter`/`check_rate_limit` need a real `CacheManager` (Redis
db 29, via the `cache_manager` fixture from `tests/conftest.py`) --
everything else here is pure. Every rate-limit test uses a fresh, unique
identifier so tests never see each other's counters in the shared db.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from shared_core.cache.manager import CacheManager
from shared_core.cache.ratelimit import RateLimitCache
from shared_core.security.ratelimit import DistributedRateLimiter

from app.models.enums import QuotaPeriod, RateLimitAlgorithm, RateLimitScope
from app.ratelimiting.engine import (
    build_identifier,
    build_rate_limiter,
    check_rate_limit,
    is_period_expired,
    is_quota_exceeded,
    quota_period_bounds,
)
from tests.conftest import ago, soon

pytestmark = pytest.mark.asyncio


def _unique_ref() -> str:
    return uuid.uuid4().hex


class TestBuildIdentifier:
    async def test_combines_scope_value_and_reference(self) -> None:
        assert build_identifier(RateLimitScope.USER, "u1") == "user:u1"

    async def test_a_missing_reference_falls_back_to_global(self) -> None:
        assert build_identifier(RateLimitScope.ORGANIZATION, None) == "organization:global"


class TestBuildRateLimiter:
    async def test_sliding_window_builds_a_distributed_rate_limiter(
        self, cache_manager: CacheManager
    ) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            max_requests=5,
            window_seconds=60,
        )
        assert isinstance(limiter, DistributedRateLimiter)

    async def test_fixed_window_builds_a_rate_limit_cache(
        self, cache_manager: CacheManager
    ) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            max_requests=5,
            window_seconds=60,
        )
        assert isinstance(limiter, RateLimitCache)

    async def test_token_bucket_also_builds_a_rate_limit_cache(
        self, cache_manager: CacheManager
    ) -> None:
        # No true token-bucket-with-refill primitive exists in shared_core (per this module's
        # own docstring), so TOKEN_BUCKET deliberately shares FIXED_WINDOW's backing.
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            max_requests=5,
            window_seconds=60,
        )
        assert isinstance(limiter, RateLimitCache)


class TestCheckRateLimitFixedWindow:
    async def test_allows_requests_under_the_limit(self, cache_manager: CacheManager) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            max_requests=2,
            window_seconds=60,
        )
        identifier = build_identifier(RateLimitScope.USER, _unique_ref())
        decision = await check_rate_limit(limiter, identifier)
        assert decision.allowed is True
        assert decision.remaining == 1

    async def test_blocks_once_the_limit_is_exceeded(self, cache_manager: CacheManager) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            max_requests=1,
            window_seconds=60,
        )
        identifier = build_identifier(RateLimitScope.USER, _unique_ref())
        await check_rate_limit(limiter, identifier)
        decision = await check_rate_limit(limiter, identifier)
        assert decision.allowed is False
        assert decision.remaining == 0
        assert decision.retry_after_seconds is not None


class TestCheckRateLimitSlidingWindow:
    async def test_allows_requests_under_the_limit(self, cache_manager: CacheManager) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            max_requests=2,
            window_seconds=60,
        )
        identifier = build_identifier(RateLimitScope.USER, _unique_ref())
        decision = await check_rate_limit(limiter, identifier)
        assert decision.allowed is True
        assert decision.remaining == 1
        assert decision.retry_after_seconds is None

    async def test_blocks_once_the_limit_is_exceeded(self, cache_manager: CacheManager) -> None:
        limiter = build_rate_limiter(
            cache_manager,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            max_requests=1,
            window_seconds=60,
        )
        identifier = build_identifier(RateLimitScope.USER, _unique_ref())
        await check_rate_limit(limiter, identifier)
        decision = await check_rate_limit(limiter, identifier)
        assert decision.allowed is False
        assert decision.remaining == 0
        # The unified decision shape never carries a retry-after hint for this algorithm.
        assert decision.retry_after_seconds is None


class TestQuotaPeriodBounds:
    async def test_daily_bounds_span_midnight_to_midnight(self) -> None:
        now = datetime(2026, 8, 5, 14, 30, tzinfo=UTC)
        start, end = quota_period_bounds(QuotaPeriod.DAILY, now)
        assert start == datetime(2026, 8, 5, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
        assert start <= now < end

    async def test_monthly_bounds_within_a_non_december_month(self) -> None:
        now = datetime(2026, 6, 15, 8, 0, tzinfo=UTC)
        start, end = quota_period_bounds(QuotaPeriod.MONTHLY, now)
        assert start == datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
        assert start <= now < end

    async def test_monthly_bounds_roll_over_the_year_in_december(self) -> None:
        now = datetime(2026, 12, 25, 8, 0, tzinfo=UTC)
        start, end = quota_period_bounds(QuotaPeriod.MONTHLY, now)
        assert start == datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
        assert end == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
        assert start <= now < end


class TestIsQuotaExceeded:
    async def test_usage_below_the_limit_is_not_exceeded(self) -> None:
        assert is_quota_exceeded(used_value=5, limit_value=10) is False

    async def test_usage_at_the_limit_is_exceeded(self) -> None:
        assert is_quota_exceeded(used_value=10, limit_value=10) is True

    async def test_usage_above_the_limit_is_exceeded(self) -> None:
        assert is_quota_exceeded(used_value=11, limit_value=10) is True


class TestIsPeriodExpired:
    async def test_a_period_ending_in_the_past_has_expired(self) -> None:
        assert is_period_expired(ago(60)) is True

    async def test_a_period_ending_in_the_future_has_not_expired(self) -> None:
        assert is_period_expired(soon(60)) is False

    async def test_a_period_ending_exactly_now_has_expired(self) -> None:
        now = datetime.now(UTC)
        assert is_period_expired(now, now=now) is True

    async def test_defaults_to_the_real_current_time_when_now_is_omitted(self) -> None:
        assert is_period_expired(ago(3600)) is True
