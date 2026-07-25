"""Tests for ``app/workers/`` -- background expiry and lease-sweep checks."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import CertificateType, LeaseStatus, SecretType
from app.models.secret_lease import SecretLease
from app.notifications.secret_notifications import SecretNotificationService
from app.repositories.certificate import CertificateRepository
from app.repositories.secret_lease import SecretLeaseRepository
from app.services.certificate import CertificateService
from app.services.lease import SecretLeaseService
from app.workers.background import run_periodic
from app.workers.expiry_worker import check_certificate_expirations, check_secret_expirations
from app.workers.lease_sweep_worker import sweep_expired_leases
from tests.conftest import build_secret_service, build_secret_version_service, make_secret
from tests.test_certificate_importer import _make_self_signed_cert as _make_cert_with_validity
from tests.test_service_certificate import _make_self_signed_cert


async def test_check_secret_expirations_marks_expired(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secrets = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await secrets.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="worker-expired",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="value",
        expires_at=datetime.now(UTC) - timedelta(days=1),
        rotation_policy={},
        metadata={},
        tags=[],
    )
    manager = AsyncMock(spec=NotificationManager)
    notifications = SecretNotificationService(manager)

    await check_secret_expirations(secrets, notifications)

    refreshed = await secrets.get_by_id(secret.id)
    assert str(refreshed.status) == "expired"


async def test_check_secret_expirations_notifies_owner_when_expiring_soon(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secrets = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    await secrets.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="worker-expiring-soon",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="value",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        rotation_policy={},
        metadata={},
        tags=[],
    )
    manager = AsyncMock(spec=NotificationManager)
    notifications = SecretNotificationService(manager)

    await check_secret_expirations(secrets, notifications)

    manager.send.assert_awaited_once()
    assert manager.send.await_args.kwargs["user_id"] == str(owner_id)


async def test_check_certificate_expirations_notifies_private_key_owner(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secrets = build_secret_service(db_session, envelope)
    certificates = CertificateService(CertificateRepository(db_session), secrets)
    owner_id = uuid.uuid4()
    now = datetime.now(UTC)

    await certificates.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="worker-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_cert_with_validity(
            not_before=now - timedelta(days=1), not_after=now + timedelta(days=1)
        ),
        chain_pem=[],
        private_key="-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
        owner_id=owner_id,
    )
    manager = AsyncMock(spec=NotificationManager)
    notifications = SecretNotificationService(manager)

    await check_certificate_expirations(certificates, secrets, notifications)

    manager.send.assert_awaited_once()
    assert manager.send.await_args.kwargs["user_id"] == str(owner_id)


async def test_check_certificate_expirations_skips_certs_without_private_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secrets = build_secret_service(db_session, envelope)
    certificates = CertificateService(CertificateRepository(db_session), secrets)

    await certificates.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="public-only-worker-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_self_signed_cert(common_name="public-only-worker.aiios.local"),
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    manager = AsyncMock(spec=NotificationManager)
    notifications = SecretNotificationService(manager)

    await check_certificate_expirations(certificates, secrets, notifications)

    manager.send.assert_not_awaited()


async def test_sweep_expired_leases_notifies_principal(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    principal_id = uuid.uuid4()
    now = datetime.now(UTC)
    lease = SecretLease(
        secret_id=secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        status=LeaseStatus.ACTIVE,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        lease_duration_seconds=3600,
    )
    db_session.add(lease)
    await db_session.flush()

    versions = build_secret_version_service(db_session, envelope)
    leases = SecretLeaseService(SecretLeaseRepository(db_session), versions)
    secrets = build_secret_service(db_session, envelope)
    manager = AsyncMock(spec=NotificationManager)
    notifications = SecretNotificationService(manager)

    await sweep_expired_leases(leases, secrets, notifications)

    manager.send.assert_awaited_once()
    assert manager.send.await_args.kwargs["user_id"] == str(principal_id)


async def test_run_periodic_executes_task_and_survives_failure() -> None:
    call_count = 0

    async def _flaky() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first iteration fails")

    task = asyncio.create_task(run_periodic("flaky", 0, _flaky))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert call_count >= 1
