"""Tests for :class:`app.services.cache.UserCacheService`, against real Redis."""

from __future__ import annotations

import uuid

from shared_core.cache.factory import CacheFramework

from app.services.cache import UserCacheService


async def test_set_then_get_returns_cached_value(cache_framework: CacheFramework) -> None:
    service = UserCacheService(cache_framework.manager)
    user_id = uuid.uuid4()

    await service.set(user_id, {"username": "alice"})
    cached = await service.get(user_id)

    assert cached == {"username": "alice"}


async def test_get_returns_none_on_miss(cache_framework: CacheFramework) -> None:
    service = UserCacheService(cache_framework.manager)

    assert await service.get(uuid.uuid4()) is None


async def test_invalidate_removes_cached_value(cache_framework: CacheFramework) -> None:
    service = UserCacheService(cache_framework.manager)
    user_id = uuid.uuid4()
    await service.set(user_id, {"username": "bob"})

    await service.invalidate(user_id)

    assert await service.get(user_id) is None


async def test_different_users_have_independent_cache_entries(
    cache_framework: CacheFramework,
) -> None:
    service = UserCacheService(cache_framework.manager)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    await service.set(user_a, {"username": "a"})
    await service.set(user_b, {"username": "b"})

    assert await service.get(user_a) == {"username": "a"}
    assert await service.get(user_b) == {"username": "b"}
