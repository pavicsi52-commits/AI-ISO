"""Tests for the smaller per-entity business services: :class:`ApiKeyService`,
:class:`DeviceService`, :class:`ServiceAccountService`, :class:`VerificationService`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.helpers.hash_helper import sha256_hex
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.email_verification import EmailVerificationToken
from app.models.trusted_device import TrustedDevice
from app.models.user import User
from app.repositories.apikey import ApiKeyRepository
from app.repositories.device import TrustedDeviceRepository
from app.repositories.service_account import ServiceAccountRepository
from app.repositories.user import UserRepository
from app.repositories.verification import EmailVerificationTokenRepository
from app.services.apikeys import ApiKeyService
from app.services.devices import DeviceService
from app.services.service_accounts import ServiceAccountService
from app.services.verification import VerificationService

# --- ApiKeyService ---


async def _make_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).create(
        User(email=f"user-{uuid.uuid4().hex}@example.com", organization_id=DEFAULT_ORGANIZATION_ID)
    )


async def test_apikey_service_create_and_authenticate(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))
    user = await _make_user(db_session)

    record, raw_key = await service.create(
        user.id, name="ci key", scopes=["read"], expires_in_days=None
    )
    authenticated = await service.authenticate(raw_key)

    assert record.user_id == user.id
    assert authenticated is not None
    assert authenticated.id == record.id
    assert authenticated.last_used_at is not None


async def test_apikey_service_authenticate_rejects_unknown_key(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))

    assert await service.authenticate("aiios_does-not-exist") is None


async def test_apikey_service_authenticate_rejects_revoked_key(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))
    user = await _make_user(db_session)
    record, raw_key = await service.create(user.id, name="ci key", scopes=[], expires_in_days=None)

    await service.revoke(user.id, record.id)

    assert await service.authenticate(raw_key) is None


async def test_apikey_service_authenticate_rejects_expired_key(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))
    user = await _make_user(db_session)
    record, raw_key = await service.create(user.id, name="ci key", scopes=[], expires_in_days=1)
    record.expires_at = datetime.now(UTC) - timedelta(days=1)

    assert await service.authenticate(raw_key) is None


async def test_apikey_service_revoke_rejects_wrong_owner(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    record, _raw_key = await service.create(
        owner.id, name="ci key", scopes=[], expires_in_days=None
    )

    with pytest.raises(NotFoundError):
        await service.revoke(other.id, record.id)


async def test_apikey_service_list_for_user(db_session: AsyncSession) -> None:
    service = ApiKeyService(ApiKeyRepository(db_session))
    user = await _make_user(db_session)
    await service.create(user.id, name="a", scopes=[], expires_in_days=None)
    await service.create(user.id, name="b", scopes=[], expires_in_days=None)

    keys = await service.list_for_user(user.id)

    assert len(keys) == 2


# --- DeviceService ---


async def test_device_service_record_login_creates_then_updates(db_session: AsyncSession) -> None:
    service = DeviceService(TrustedDeviceRepository(db_session))
    user = await _make_user(db_session)

    first = await service.record_login(
        user.id, device_fingerprint="fp-1", ip_address="1.1.1.1", location="US"
    )
    second = await service.record_login(
        user.id, device_fingerprint="fp-1", ip_address="2.2.2.2", location="CA"
    )

    assert first.id == second.id
    assert second.ip_address == "2.2.2.2"
    assert second.location == "CA"


def test_device_service_mark_trusted_and_is_currently_trusted(db_session: AsyncSession) -> None:
    service = DeviceService(TrustedDeviceRepository(db_session))
    device = TrustedDevice(
        user_id=uuid.uuid4(),
        device_fingerprint="fp-2",
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    assert service.is_currently_trusted(device) is False
    service.mark_trusted(device)
    assert service.is_currently_trusted(device) is True

    device.revoked_at = datetime.now(UTC)
    assert service.is_currently_trusted(device) is False


async def test_device_service_revoke_rejects_wrong_owner(db_session: AsyncSession) -> None:
    service = DeviceService(TrustedDeviceRepository(db_session))
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    device = await service.record_login(owner.id, device_fingerprint="fp-3")

    with pytest.raises(NotFoundError):
        await service.revoke(other.id, device.id)


async def test_device_service_revoke_marks_untrusted(db_session: AsyncSession) -> None:
    service = DeviceService(TrustedDeviceRepository(db_session))
    user = await _make_user(db_session)
    device = await service.record_login(user.id, device_fingerprint="fp-4")
    service.mark_trusted(device)

    await service.revoke(user.id, device.id)

    assert device.is_trusted is False
    assert device.revoked_at is not None


async def test_device_service_list_for_user(db_session: AsyncSession) -> None:
    service = DeviceService(TrustedDeviceRepository(db_session))
    user = await _make_user(db_session)
    await service.record_login(user.id, device_fingerprint="fp-5")

    devices = await service.list_for_user(user.id)

    assert len(devices) == 1


# --- ServiceAccountService ---


async def test_service_account_lifecycle(db_session: AsyncSession) -> None:
    service = ServiceAccountService(ServiceAccountRepository(db_session))

    record, raw_token = await service.create(
        name=f"svc-{uuid.uuid4().hex}", description="ci", scopes=["read"]
    )
    authenticated = await service.authenticate(raw_token)
    assert authenticated is not None
    assert authenticated.last_used_at is not None

    rotated, new_token = await service.rotate(record.id)
    assert rotated.id == record.id
    assert await service.authenticate(raw_token) is None
    assert (await service.authenticate(new_token)) is not None

    await service.disable(record.id)
    assert await service.authenticate(new_token) is None


async def test_service_account_authenticate_rejects_unknown_token(
    db_session: AsyncSession,
) -> None:
    service = ServiceAccountService(ServiceAccountRepository(db_session))

    assert await service.authenticate("does-not-exist") is None


# --- VerificationService ---


async def test_verification_service_create_and_consume(db_session: AsyncSession) -> None:
    service = VerificationService(EmailVerificationTokenRepository(db_session))
    user = await _make_user(db_session)

    raw_token = await service.create_token(user)
    record = await service.consume(raw_token)

    assert record.user_id == user.id
    assert record.used_at is not None


async def test_verification_service_consume_rejects_reuse(db_session: AsyncSession) -> None:
    service = VerificationService(EmailVerificationTokenRepository(db_session))
    user = await _make_user(db_session)
    raw_token = await service.create_token(user)
    await service.consume(raw_token)

    with pytest.raises(AuthenticationError):
        await service.consume(raw_token)


async def test_verification_service_consume_rejects_unknown_token(
    db_session: AsyncSession,
) -> None:
    service = VerificationService(EmailVerificationTokenRepository(db_session))

    with pytest.raises(AuthenticationError):
        await service.consume("does-not-exist")


async def test_verification_service_consume_rejects_expired_token(
    db_session: AsyncSession,
) -> None:
    service = VerificationService(EmailVerificationTokenRepository(db_session))
    user = await _make_user(db_session)
    raw_token = "expired-verification-token"
    await EmailVerificationTokenRepository(db_session).create(
        EmailVerificationToken(
            user_id=user.id,
            email=user.email,
            token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    with pytest.raises(AuthenticationError):
        await service.consume(raw_token)
