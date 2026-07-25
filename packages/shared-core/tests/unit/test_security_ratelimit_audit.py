"""Tests for the distributed rate limiter and security audit logging."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from shared_core.cache.manager import CacheManager
from shared_core.security.audit import SecurityAuditEventType, audit_security_event
from shared_core.security.ratelimit import DistributedRateLimiter, rate_limit_key


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def cache_manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


def test_rate_limit_key_combines_scope_and_identifier() -> None:
    assert rate_limit_key(scope="user", identifier="user-42") == "user:user-42"


async def test_distributed_rate_limiter_allows_within_limit(cache_manager: CacheManager) -> None:
    limiter = DistributedRateLimiter(cache_manager, max_requests=3, window_seconds=60)
    key = rate_limit_key(scope="ip", identifier="1.2.3.4")

    assert await limiter.allow(key) is True
    assert await limiter.allow(key) is True
    assert await limiter.allow(key) is True


async def test_distributed_rate_limiter_blocks_over_limit(cache_manager: CacheManager) -> None:
    limiter = DistributedRateLimiter(cache_manager, max_requests=2, window_seconds=60)
    key = rate_limit_key(scope="ip", identifier="1.2.3.4")

    await limiter.allow(key)
    await limiter.allow(key)

    assert await limiter.allow(key) is False


async def test_distributed_rate_limiter_tracks_keys_independently(
    cache_manager: CacheManager,
) -> None:
    limiter = DistributedRateLimiter(cache_manager, max_requests=1, window_seconds=60)

    assert await limiter.allow(rate_limit_key(scope="ip", identifier="1.1.1.1")) is True
    assert await limiter.allow(rate_limit_key(scope="ip", identifier="2.2.2.2")) is True


async def test_distributed_rate_limiter_remaining_decreases_with_use(
    cache_manager: CacheManager,
) -> None:
    limiter = DistributedRateLimiter(cache_manager, max_requests=3, window_seconds=60)
    key = rate_limit_key(scope="ip", identifier="1.2.3.4")

    assert await limiter.remaining(key) == 3
    await limiter.allow(key)
    assert await limiter.remaining(key) == 2


async def test_distributed_rate_limiter_remaining_never_negative(
    cache_manager: CacheManager,
) -> None:
    limiter = DistributedRateLimiter(cache_manager, max_requests=1, window_seconds=60)
    key = rate_limit_key(scope="ip", identifier="1.2.3.4")

    await limiter.allow(key)
    await limiter.allow(key)  # blocked, but still recorded as an attempt

    assert await limiter.remaining(key) >= 0


def test_audit_security_event_logs_at_the_security_level(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="shared_core.security.audit"):
        audit_security_event(SecurityAuditEventType.FAILED_LOGIN, actor_id="user-1", ip="1.2.3.4")

    record = caplog.records[-1]
    assert record.extra_fields["category"] == "security"
    assert record.extra_fields["event"] == "failed_login"
    assert record.extra_fields["actor_id"] == "user-1"
    assert record.extra_fields["ip"] == "1.2.3.4"


def test_audit_security_event_default_outcome_is_success(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="shared_core.security.audit"):
        audit_security_event(SecurityAuditEventType.LOGIN, actor_id="user-1")

    assert caplog.records[-1].extra_fields["outcome"] == "success"


def test_audit_security_event_supports_every_event_type(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="shared_core.security.audit"):
        for event_type in SecurityAuditEventType:
            audit_security_event(event_type)

    assert len(caplog.records) == len(SecurityAuditEventType)
