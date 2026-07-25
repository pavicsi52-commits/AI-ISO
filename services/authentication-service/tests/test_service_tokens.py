"""Tests for :class:`app.services.tokens.TokenService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.session import Session
from app.models.user import User
from app.repositories.session import SessionRepository
from app.repositories.token import AccessTokenRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.tokens import TokenService


def _service(db_session: AsyncSession, jwt_keypair: tuple[str, str]) -> TokenService:
    private_key, public_key = jwt_keypair
    return TokenService(
        AccessTokenRepository(db_session),
        RefreshTokenRepository(db_session),
        private_key=private_key,
        public_key=public_key,
    )


async def _make_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).create(
        User(email=f"user-{uuid.uuid4().hex}@example.com", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def _make_session(db_session: AsyncSession, user_id: uuid.UUID) -> Session:
    now = datetime.now(UTC)
    return await SessionRepository(db_session).create(
        Session(
            user_id=user_id,
            session_id=str(uuid.uuid4()),
            last_active_at=now,
            expires_at=now + timedelta(hours=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )


async def test_issue_creates_tracked_access_and_refresh_tokens(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)

    pair = await service.issue(user.id)

    claims = await service.decode_access_token(pair.access_token)
    assert claims["sub"] == str(user.id)


async def test_decode_access_token_rejects_revoked_token(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)
    pair = await service.issue(user.id)
    claims = await service.decode_access_token(pair.access_token)

    await service.revoke_access_token(str(claims["jti"]))

    with pytest.raises(AuthenticationError):
        await service.decode_access_token(pair.access_token)


async def test_decode_refresh_token_rejects_access_token(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)
    pair = await service.issue(user.id)

    with pytest.raises(AuthenticationError):
        await service.decode_refresh_token(pair.access_token)


async def test_refresh_rotates_token_and_revokes_old_one(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)
    pair = await service.issue(user.id)

    new_pair = await service.refresh(pair.refresh_token)

    assert new_pair.refresh_token != pair.refresh_token
    with pytest.raises(AuthenticationError):
        await service.refresh(pair.refresh_token)


async def test_refresh_rejects_access_token(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)
    pair = await service.issue(user.id)

    with pytest.raises(AuthenticationError):
        await service.refresh(pair.access_token)


async def test_revoke_refresh_token_returns_tracked_session_id(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)
    user = await _make_user(db_session)
    session = await _make_session(db_session, user.id)
    pair = await service.issue(user.id, session_id=session.id)
    claims = await service.decode_refresh_token(pair.refresh_token)

    returned_session_id = await service.revoke_refresh_token(str(claims["jti"]))

    assert returned_session_id == session.id


async def test_revoke_refresh_token_with_unknown_jti_returns_none(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)

    assert await service.revoke_refresh_token("does-not-exist") is None


async def test_revoke_access_token_with_unknown_jti_is_a_no_op(
    db_session: AsyncSession, jwt_keypair: tuple[str, str]
) -> None:
    service = _service(db_session, jwt_keypair)

    await service.revoke_access_token("does-not-exist")
