"""Direct service-layer tests for ``app/services/secret.py`` -- the
crypto-critical orchestrator. Every test runs against a real Postgres
session and real AES-256-GCM envelope encryption, no mocking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import RotationOutcome, RotationTrigger, SecretStatus, SecretType
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_rotation import SecretRotationRepository
from app.repositories.secret_tag import SecretTagRepository
from tests.conftest import build_secret_service, build_secret_version_service


async def test_create_stores_ciphertext_not_plaintext(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="db-password",
        description=None,
        category_id=None,
        secret_type=SecretType.PASSWORD,
        owner_id=owner_id,
        value="hunter2",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    assert secret.current_version == 1
    assert secret.status == SecretStatus.ACTIVE

    versions = build_secret_version_service(db_session, envelope)
    current = await versions.get_current(secret.id)
    assert current.ciphertext != "hunter2"
    assert "hunter2" not in current.ciphertext


async def test_create_with_tags_assigns_them(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="tagged-secret",
        description=None,
        category_id=None,
        secret_type=SecretType.API_KEY,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=["prod", "critical"],
    )
    assigned = await SecretTagRepository(db_session).list_for_secret(secret.id)
    assert {tag.label for tag in assigned} == {"prod", "critical"}


async def test_get_decrypted_round_trips_value(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="round-trip",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="correct horse battery staple",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )

    fetched, value = await service.get_decrypted(secret.id, actor_id=owner_id)
    assert fetched.id == secret.id
    assert value == "correct horse battery staple"


async def test_get_decrypted_records_audit_without_value(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="audited",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="do-not-leak-me",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )

    await service.get_decrypted(secret.id, actor_id=owner_id)

    entries = await SecretAuditRepository(db_session).list_for_secret(secret.id)
    read_entries = [entry for entry in entries if entry.action == "read"]
    assert len(read_entries) == 1
    assert "do-not-leak-me" not in str(read_entries[0].before)
    assert "do-not-leak-me" not in str(read_entries[0].after)


async def test_update_changes_metadata_not_value(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="original-name",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=owner_id,
        value="stays-the-same",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )

    updated = await service.update(
        secret.id,
        actor_id=owner_id,
        name="new-name",
        description="new description",
        category_id=None,
        status=SecretStatus.DISABLED,
        expires_at=None,
        rotation_policy={},
        metadata={"env": "prod"},
    )
    assert updated.name == "new-name"
    assert updated.status == SecretStatus.DISABLED
    assert updated.metadata_ == {"env": "prod"}

    _fetched, value = await service.get_decrypted(secret.id, actor_id=owner_id)
    assert value == "stays-the-same"


async def test_rotate_creates_new_version_and_history(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="rotatable",
        description=None,
        category_id=None,
        secret_type=SecretType.PASSWORD,
        owner_id=owner_id,
        value="old-password",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    assert secret.current_version == 1

    rotated = await service.rotate(secret.id, new_value="new-password", rotated_by=owner_id)
    assert rotated.current_version == 2

    _fetched, value = await service.get_decrypted(secret.id, actor_id=owner_id)
    assert value == "new-password"

    history = await SecretRotationRepository(db_session).list_for_secret(secret.id)
    assert len(history) == 1
    assert history[0].outcome == RotationOutcome.SUCCESS
    assert history[0].trigger == RotationTrigger.MANUAL
    assert history[0].previous_version_number == 1
    assert history[0].new_version_number == 2


async def test_rotate_old_version_still_decryptable(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    """Rotation must not destroy prior versions ("Previous Versions")."""
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="history-preserved",
        description=None,
        category_id=None,
        secret_type=SecretType.PASSWORD,
        owner_id=owner_id,
        value="version-one",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    await service.rotate(secret.id, new_value="version-two", rotated_by=owner_id)

    versions = build_secret_version_service(db_session, envelope)
    old_version = await versions.get_by_number(secret.id, 1)
    assert await versions.decrypt(old_version) == "version-one"


async def test_delete_soft_deletes_and_audits(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="to-delete",
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
    await service.delete(secret.id, actor_id=owner_id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(secret.id)

    entries = await SecretAuditRepository(db_session).list_for_secret(secret.id)
    assert any(entry.action == "delete" for entry in entries)


async def test_mark_expired_transitions_status(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="expirable",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    expired = await service.mark_expired(secret.id)
    assert expired.status == SecretStatus.EXPIRED

    # Idempotent -- marking an already-expired secret expired again is a no-op.
    expired_again = await service.mark_expired(secret.id)
    assert expired_again.status == SecretStatus.EXPIRED


async def test_is_expired_true_when_past_expiry(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    now = datetime.now(UTC)
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="soon-expired",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=now - timedelta(days=1),
        rotation_policy={},
        metadata={},
        tags=[],
    )
    assert await service.is_expired(secret, now=now) is True


async def test_is_expired_false_when_no_expiry_set(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="never-expires",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    assert await service.is_expired(secret) is False


async def test_list_expiring_before_finds_active_secrets(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    expiring_soon = await service.create(
        organization_id=org_id,
        project_id=None,
        name="expiring-soon",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=now + timedelta(days=1),
        rotation_policy={},
        metadata={},
        tags=[],
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        name="expiring-later",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=now + timedelta(days=100),
        rotation_policy={},
        metadata={},
        tags=[],
    )

    results = await service.list_expiring_before(now + timedelta(days=7))
    assert [r.id for r in results] == [expiring_soon.id]


async def test_list_for_org_scopes_correctly(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    await service.create(
        organization_id=org_a,
        project_id=None,
        name="org-a-secret",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )
    await service.create(
        organization_id=org_b,
        project_id=None,
        name="org-b-secret",
        description=None,
        category_id=None,
        secret_type=SecretType.CUSTOM,
        owner_id=uuid.uuid4(),
        value="value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )

    results = await service.list_for_org(org_a)
    assert len(results) == 1
    assert results[0].name == "org-a-secret"


async def test_get_by_id_not_found(db_session: AsyncSession, envelope: EnvelopeEncryption) -> None:
    service = build_secret_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())
