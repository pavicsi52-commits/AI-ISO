"""Tests for the Redis-backed session manager."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from shared_core.cache.manager import CacheManager
from shared_core.security.sessions import SessionManager


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def cache_manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


@pytest.fixture
def session_manager(cache_manager: CacheManager) -> SessionManager:
    return SessionManager(
        cache_manager,
        idle_timeout_seconds=1800,
        absolute_timeout_seconds=28800,
        max_concurrent_sessions=3,
    )


async def test_create_session_returns_a_new_session(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1", ip_address="1.2.3.4")

    assert session.user_id == "user-1"
    assert session.ip_address == "1.2.3.4"
    assert session.revoked is False


async def test_get_session_returns_the_stored_session(session_manager: SessionManager) -> None:
    created = await session_manager.create_session(user_id="user-1")

    fetched = await session_manager.get_session(created.session_id)

    assert fetched is not None
    assert fetched.session_id == created.session_id


async def test_get_session_returns_none_for_unknown_id(session_manager: SessionManager) -> None:
    assert await session_manager.get_session("does-not-exist") is None


async def test_validate_session_passes_for_fresh_session(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1")

    validated = await session_manager.validate_session(session.session_id)

    assert validated is not None


async def test_validate_session_fails_for_revoked_session(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1")
    await session_manager.revoke_session(session.session_id)

    assert await session_manager.validate_session(session.session_id) is None


async def test_validate_session_fails_for_idle_timeout(cache_manager: CacheManager) -> None:
    manager = SessionManager(
        cache_manager,
        idle_timeout_seconds=0,
        absolute_timeout_seconds=28800,
        max_concurrent_sessions=3,
    )
    session = await manager.create_session(user_id="user-1")

    await asyncio.sleep(0.01)

    assert await manager.validate_session(session.session_id) is None


async def test_validate_session_fails_for_absolute_timeout(cache_manager: CacheManager) -> None:
    # `absolute_timeout_seconds` doubles as the Redis TTL for the stored
    # session (see `SessionManager._store`), and Redis rejects `EX 0` --
    # so this uses a small positive value and a real sleep past it,
    # rather than 0.
    manager = SessionManager(
        cache_manager,
        idle_timeout_seconds=28800,
        absolute_timeout_seconds=1,
        max_concurrent_sessions=3,
    )
    session = await manager.create_session(user_id="user-1")

    await asyncio.sleep(1.1)

    assert await manager.validate_session(session.session_id) is None


async def test_refresh_session_extends_idle_timeout(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1")

    refreshed = await session_manager.refresh_session(session.session_id)

    assert refreshed is not None
    assert refreshed.last_active_at >= session.last_active_at


async def test_refresh_session_returns_none_for_invalid_session(
    session_manager: SessionManager,
) -> None:
    assert await session_manager.refresh_session("does-not-exist") is None


async def test_revoke_session_marks_it_revoked(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1")

    await session_manager.revoke_session(session.session_id)
    stored = await session_manager.get_session(session.session_id)

    assert stored is not None
    assert stored.revoked is True


async def test_revoke_session_on_unknown_id_does_not_raise(
    session_manager: SessionManager,
) -> None:
    await session_manager.revoke_session("does-not-exist")  # should not raise


async def test_terminate_session_removes_it_entirely(session_manager: SessionManager) -> None:
    session = await session_manager.create_session(user_id="user-1")

    await session_manager.terminate_session(session.session_id)

    assert await session_manager.get_session(session.session_id) is None


async def test_concurrent_session_limit_evicts_oldest(session_manager: SessionManager) -> None:
    first = await session_manager.create_session(user_id="user-1", device_id="device-1")
    await session_manager.create_session(user_id="user-1", device_id="device-2")
    await session_manager.create_session(user_id="user-1", device_id="device-3")

    # A 4th session should evict the first (oldest).
    await session_manager.create_session(user_id="user-1", device_id="device-4")

    assert await session_manager.get_session(first.session_id) is None
