"""Tests for :class:`app.cache.authorization_cache.AuthorizationCacheService`."""

from __future__ import annotations

import uuid

from shared_core.cache.factory import CacheFramework

from app.cache.authorization_cache import AuthorizationCacheService
from app.constants import DEFAULT_ORGANIZATION_ID


def _service(cache_framework: CacheFramework) -> AuthorizationCacheService:
    return AuthorizationCacheService(cache_framework.manager, ttl_seconds=60)


async def test_cache_miss_returns_none(cache_framework: CacheFramework) -> None:
    service = _service(cache_framework)

    result = await service.get_permissions(uuid.uuid4(), DEFAULT_ORGANIZATION_ID, None)

    assert result is None


async def test_set_then_get_permissions(cache_framework: CacheFramework) -> None:
    service = _service(cache_framework)
    user_id = uuid.uuid4()

    await service.set_permissions(user_id, DEFAULT_ORGANIZATION_ID, None, ["users:read"])
    cached = await service.get_permissions(user_id, DEFAULT_ORGANIZATION_ID, None)

    assert cached == ["users:read"]


async def test_invalidate_user_evicts_cache(cache_framework: CacheFramework) -> None:
    service = _service(cache_framework)
    user_id = uuid.uuid4()
    await service.set_permissions(user_id, DEFAULT_ORGANIZATION_ID, None, ["users:read"])

    await service.invalidate_user(user_id, DEFAULT_ORGANIZATION_ID)

    assert await service.get_permissions(user_id, DEFAULT_ORGANIZATION_ID, None) is None


async def test_cache_keys_distinguish_project_scope(cache_framework: CacheFramework) -> None:
    service = _service(cache_framework)
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    await service.set_permissions(user_id, DEFAULT_ORGANIZATION_ID, None, ["global:read"])
    await service.set_permissions(user_id, DEFAULT_ORGANIZATION_ID, project_id, ["project:read"])

    assert await service.get_permissions(user_id, DEFAULT_ORGANIZATION_ID, None) == ["global:read"]
    assert await service.get_permissions(user_id, DEFAULT_ORGANIZATION_ID, project_id) == [
        "project:read"
    ]
