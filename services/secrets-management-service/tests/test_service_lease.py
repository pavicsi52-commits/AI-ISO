"""Direct service-layer tests for ``app/services/lease.py``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.events.secret_events import LeaseCreatedEvent, LeaseExpiredEvent
from app.models.enums import LeaseStatus, SecretType
from app.models.secret_lease import SecretLease
from app.repositories.secret_lease import SecretLeaseRepository
from app.services.lease import SecretLeaseService
from tests.conftest import build_secret_service, build_secret_version_service, make_secret


def _lease_service(
    db_session: AsyncSession, envelope: EnvelopeEncryption, **kwargs: object
) -> SecretLeaseService:
    versions = build_secret_version_service(db_session, envelope)
    return SecretLeaseService(SecretLeaseRepository(db_session), versions, **kwargs)  # type: ignore[arg-type]


async def test_issue_returns_decrypted_current_value(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secrets = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await secrets.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="leasable",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="leased-value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    leases = _lease_service(db_session, envelope)

    lease, value = await leases.issue(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=owner_id,
        duration_seconds=3600,
    )
    assert value == "leased-value"
    assert lease.status == LeaseStatus.ACTIVE
    assert lease.expires_at > lease.issued_at


async def test_issue_raises_when_secret_has_no_version(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    leases = _lease_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await leases.issue(
            secret.id,
            organization_id=secret.organization_id,
            principal_id=uuid.uuid4(),
            duration_seconds=60,
        )


async def test_revoke_marks_lease_revoked(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    lease = SecretLease(
        secret_id=secret.id,
        organization_id=secret.organization_id,
        principal_id=uuid.uuid4(),
        status=LeaseStatus.ACTIVE,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        lease_duration_seconds=3600,
    )
    db_session.add(lease)
    await db_session.flush()

    leases = _lease_service(db_session, envelope)
    revoked = await leases.revoke(lease.id)
    assert revoked.status == LeaseStatus.REVOKED


async def test_revoke_raises_when_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    leases = _lease_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await leases.revoke(uuid.uuid4())


async def test_sweep_expired_marks_past_due_leases(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret_1 = await make_secret(db_session)
    secret_2 = await make_secret(db_session)
    now = datetime.now(UTC)
    expired_lease = SecretLease(
        secret_id=secret_1.id,
        organization_id=secret_1.organization_id,
        principal_id=uuid.uuid4(),
        status=LeaseStatus.ACTIVE,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        lease_duration_seconds=3600,
    )
    active_lease = SecretLease(
        secret_id=secret_2.id,
        organization_id=secret_2.organization_id,
        principal_id=uuid.uuid4(),
        status=LeaseStatus.ACTIVE,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        lease_duration_seconds=3600,
    )
    db_session.add_all([expired_lease, active_lease])
    await db_session.flush()

    leases = _lease_service(db_session, envelope)
    swept = await leases.sweep_expired(now=now)

    assert {lease.id for lease in swept} == {expired_lease.id}
    assert expired_lease.status == LeaseStatus.EXPIRED
    assert active_lease.status == LeaseStatus.ACTIVE


async def test_issue_publishes_lease_created_event(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    captured: list[object] = []

    async def _publish(event: object) -> None:
        captured.append(event)

    secrets = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await secrets.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="event-lease",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    leases = _lease_service(db_session, envelope, publish_event=_publish)
    await leases.issue(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=owner_id,
        duration_seconds=60,
    )
    assert any(isinstance(event, LeaseCreatedEvent) for event in captured)


async def test_sweep_expired_publishes_lease_expired_event(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    captured: list[object] = []

    async def _publish(event: object) -> None:
        captured.append(event)

    secret = await make_secret(db_session)
    now = datetime.now(UTC)
    lease = SecretLease(
        secret_id=secret.id,
        organization_id=secret.organization_id,
        principal_id=uuid.uuid4(),
        status=LeaseStatus.ACTIVE,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        lease_duration_seconds=3600,
    )
    db_session.add(lease)
    await db_session.flush()

    leases = _lease_service(db_session, envelope, publish_event=_publish)
    await leases.sweep_expired(now=now)
    assert any(isinstance(event, LeaseExpiredEvent) for event in captured)
