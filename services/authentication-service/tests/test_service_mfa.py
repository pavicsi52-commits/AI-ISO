"""Tests for :class:`app.services.mfa.MfaService`."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.user import User
from app.repositories.mfa import MfaDeviceRepository
from app.repositories.user import UserRepository
from app.services.mfa import MfaService


def _service(db_session: AsyncSession) -> MfaService:
    return MfaService(MfaDeviceRepository(db_session))


async def _make_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).create(
        User(email=f"user-{uuid.uuid4().hex}@example.com", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_enable_creates_unverified_primary_device_with_recovery_codes(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)

    device, codes = await service.enable(user.id)

    assert device.is_primary is True
    assert device.is_verified is False
    assert len(codes) == len(device.recovery_codes_hashed or [])
    assert await service.has_verified_device(user.id) is False


def test_build_otpauth_uri_contains_secret_and_issuer(db_session: AsyncSession) -> None:
    service = _service(db_session)

    uri = service.build_otpauth_uri("ABC123", email="user@example.com")

    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC123" in uri
    assert "issuer=AI-IOS" in uri


async def test_confirm_enrollment_with_correct_code_marks_device_verified(
    db_session: AsyncSession, totp_code: Callable[[str], str]
) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    device, _codes = await service.enable(user.id)

    confirmed = await service.confirm_enrollment(user.id, totp_code(device.secret))

    assert confirmed.is_verified is True
    assert await service.has_verified_device(user.id) is True


async def test_confirm_enrollment_with_wrong_code_raises(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    await service.enable(user.id)

    with pytest.raises(AuthenticationError):
        await service.confirm_enrollment(user.id, "000000")


async def test_confirm_enrollment_with_no_pending_device_raises(db_session: AsyncSession) -> None:
    service = _service(db_session)

    with pytest.raises(AuthenticationError):
        await service.confirm_enrollment(uuid.uuid4(), "000000")


async def test_verify_with_totp_code_updates_last_used(
    db_session: AsyncSession, totp_code: Callable[[str], str]
) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    device, _codes = await service.enable(user.id)
    await service.confirm_enrollment(user.id, totp_code(device.secret))

    assert await service.verify(user.id, totp_code(device.secret)) is True
    assert device.last_used_at is not None


async def test_verify_with_recovery_code_consumes_it(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    device, codes = await service.enable(user.id)
    device.is_verified = True
    recovery_code = codes[0]

    assert await service.verify(user.id, recovery_code) is True
    assert await service.verify(user.id, recovery_code) is False


async def test_verify_returns_false_for_unverified_device(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    await service.enable(user.id)

    assert await service.verify(user.id, "000000") is False


async def test_verify_returns_false_with_no_device(db_session: AsyncSession) -> None:
    service = _service(db_session)

    assert await service.verify(uuid.uuid4(), "000000") is False


async def test_disable_removes_every_device(db_session: AsyncSession) -> None:
    service = _service(db_session)
    user = await _make_user(db_session)
    await service.enable(user.id)

    await service.disable(user.id)

    assert await service.has_verified_device(user.id) is False
