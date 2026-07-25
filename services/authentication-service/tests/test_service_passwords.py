"""Tests for :class:`app.services.passwords.PasswordService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.validation import ValidationError
from shared_core.helpers.hash_helper import sha256_hex
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.password import PasswordResetToken
from app.models.user import User
from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository
from app.repositories.user import UserRepository
from app.services.passwords import PasswordService


def _service(db_session: AsyncSession, *, max_age_days: int | None = None) -> PasswordService:
    return PasswordService(
        PasswordHistoryRepository(db_session),
        PasswordResetTokenRepository(db_session),
        history_size=3,
        max_age_days=max_age_days,
    )


async def _make_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).create(
        User(email=f"user-{uuid.uuid4().hex}@example.com", organization_id=DEFAULT_ORGANIZATION_ID)
    )


def test_hash_and_verify_round_trip(db_session: AsyncSession) -> None:
    service = _service(db_session)

    hashed = service.hash("Sup3rSecret!23")

    assert service.verify("Sup3rSecret!23", hashed) is True
    assert service.verify("wrong-password", hashed) is False


def test_needs_rehash_reflects_current_parameters(db_session: AsyncSession) -> None:
    service = _service(db_session)
    hashed = service.hash("Sup3rSecret!23")

    assert service.needs_rehash(hashed) is False


def test_check_expired_returns_false_when_no_max_age_configured(db_session: AsyncSession) -> None:
    service = _service(db_session, max_age_days=None)

    assert service.check_expired(last_changed_at=datetime.now(UTC) - timedelta(days=9999)) is False


def test_check_expired_true_past_max_age(db_session: AsyncSession) -> None:
    service = _service(db_session, max_age_days=90)

    assert service.check_expired(last_changed_at=datetime.now(UTC) - timedelta(days=91)) is True
    assert service.check_expired(last_changed_at=datetime.now(UTC) - timedelta(days=1)) is False


async def test_require_not_reused_raises_on_recent_match(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    hashed = service.hash("Sup3rSecret!23")
    await service.record(user.id, hashed)

    with pytest.raises(ValidationError):
        await service.require_not_reused(user.id, "Sup3rSecret!23")

    await service.require_not_reused(user.id, "SomethingElse!99")


async def test_create_and_consume_reset_token(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)

    raw_token = await service.create_reset_token(user)
    record = await service.consume_reset_token(raw_token)

    assert record.user_id == user.id
    assert record.used_at is not None


async def test_consume_reset_token_rejects_reuse(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    raw_token = await service.create_reset_token(user)
    await service.consume_reset_token(raw_token)

    with pytest.raises(AuthenticationError):
        await service.consume_reset_token(raw_token)


async def test_consume_reset_token_rejects_unknown_token(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(AuthenticationError):
        await service.consume_reset_token("does-not-exist")


async def test_consume_reset_token_rejects_expired_token(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    raw_token = "expired-raw-token"
    await PasswordResetTokenRepository(db_session).create(
        PasswordResetToken(
            user_id=user.id,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    with pytest.raises(AuthenticationError):
        await service.consume_reset_token(raw_token)
