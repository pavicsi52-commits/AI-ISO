"""Tests for :class:`app.services.sessions.SessionService`."""

from __future__ import annotations

import uuid

from shared_core.constants.authentication import AuthConstants
from shared_core.security.sessions import SessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.user import User
from app.repositories.session import SessionRepository
from app.repositories.user import UserRepository
from app.services.sessions import SessionService


def _service(db_session: AsyncSession, session_manager: SessionManager) -> SessionService:
    return SessionService(
        SessionRepository(db_session),
        session_manager,
        absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
    )


async def _make_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).create(
        User(email=f"user-{uuid.uuid4().hex}@example.com", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_create_tracks_session_in_both_redis_and_postgres(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)
    user = await _make_user(db_session)

    record = await service.create(user.id, ip_address="127.0.0.1", user_agent="pytest")

    assert record.user_id == user.id
    assert await service.is_valid(record.session_id) is True


async def test_is_valid_false_for_unknown_session(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)

    assert await service.is_valid(str(uuid.uuid4())) is False


async def test_refresh_extends_session_and_updates_db_record(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)
    user = await _make_user(db_session)
    record = await service.create(user.id)

    await service.refresh(record.session_id)

    assert await service.is_valid(record.session_id) is True


async def test_refresh_on_unknown_session_is_a_no_op(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)

    await service.refresh(str(uuid.uuid4()))


async def test_terminate_revokes_session_in_redis_and_marks_db_record(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)
    user = await _make_user(db_session)
    record = await service.create(user.id)

    await service.terminate(record.session_id, reason="logout")

    assert await service.is_valid(record.session_id) is False
    reloaded = await service.get_by_db_id(record.id)
    assert reloaded is not None
    assert reloaded.revoked_at is not None
    assert reloaded.revoked_reason == "logout"


async def test_terminate_all_for_user_revokes_every_active_session(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)
    user = await _make_user(db_session)
    first = await service.create(user.id)
    second = await service.create(user.id)

    count = await service.terminate_all_for_user(user.id)

    assert count == 2
    assert await service.is_valid(first.session_id) is False
    assert await service.is_valid(second.session_id) is False
    assert await service.list_active(user.id) == []


async def test_get_by_db_id_returns_none_for_unknown_id(
    db_session: AsyncSession, session_manager: SessionManager
) -> None:
    service = _service(db_session, session_manager)

    assert await service.get_by_db_id(uuid.uuid4()) is None
