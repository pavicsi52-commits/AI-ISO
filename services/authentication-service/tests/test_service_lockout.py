"""Tests for :class:`app.services.lockout.LockoutService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import FailedLoginReason
from app.models.user import User
from app.repositories.failed_login import FailedLoginRepository
from app.services.lockout import LockoutService


def _service(db_session: AsyncSession) -> LockoutService:
    return LockoutService(FailedLoginRepository(db_session))


async def _fail(service: LockoutService, identifier: str, times: int) -> None:
    for _ in range(times):
        await service.record_failure(identifier, reason=FailedLoginReason.INVALID_CREDENTIALS)


async def test_recent_failure_count_starts_at_zero(db_session: AsyncSession) -> None:
    service = _service(db_session)

    assert await service.recent_failure_count(f"id-{uuid.uuid4()}") == 0


async def test_record_failure_increments_recent_count(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    await _fail(service, identifier, 2)

    assert await service.recent_failure_count(identifier) == 2


async def test_captcha_required_at_threshold(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    await _fail(service, identifier, 2)
    assert await service.captcha_required(identifier) is False

    await _fail(service, identifier, 1)
    assert await service.captcha_required(identifier) is True


async def test_compute_delay_seconds_grows_and_caps(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    assert await service.compute_delay_seconds(identifier) == 0.0

    await _fail(service, identifier, 1)
    first_delay = await service.compute_delay_seconds(identifier)
    await _fail(service, identifier, 9)
    capped_delay = await service.compute_delay_seconds(identifier)

    assert first_delay == 2.0
    assert capped_delay == 30.0


async def test_compute_lockout_until_none_below_threshold(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    await _fail(service, identifier, 4)

    assert await service.compute_lockout_until(identifier) is None


async def test_compute_lockout_until_temporary_at_threshold(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    await _fail(service, identifier, 5)
    lockout_until = await service.compute_lockout_until(identifier)

    assert lockout_until is not None
    delta = lockout_until - datetime.now(UTC)
    assert timedelta(minutes=10) < delta <= timedelta(minutes=15)


async def test_compute_lockout_until_permanent_at_threshold(db_session: AsyncSession) -> None:
    service = _service(db_session)
    identifier = f"id-{uuid.uuid4()}"

    await _fail(service, identifier, 10)
    lockout_until = await service.compute_lockout_until(identifier)

    assert lockout_until is not None
    assert lockout_until - datetime.now(UTC) > timedelta(days=300)


def test_is_locked_reflects_locked_until(db_session: AsyncSession) -> None:
    service = _service(db_session)
    unlocked_user = User(
        email="a@example.com", organization_id=DEFAULT_ORGANIZATION_ID, locked_until=None
    )
    locked_user = User(
        email="b@example.com",
        organization_id=DEFAULT_ORGANIZATION_ID,
        locked_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    expired_lock_user = User(
        email="c@example.com",
        organization_id=DEFAULT_ORGANIZATION_ID,
        locked_until=datetime.now(UTC) - timedelta(minutes=5),
    )

    assert service.is_locked(unlocked_user) is False
    assert service.is_locked(locked_user) is True
    assert service.is_locked(expired_lock_user) is False
