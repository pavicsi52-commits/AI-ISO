"""Direct service-layer tests for ``app/services/encryption_key.py``."""

from __future__ import annotations

import uuid

import pytest
from cryptography.exceptions import InvalidTag
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.events.secret_events import KeyGeneratedEvent, KeyRevokedEvent
from app.models.enums import EncryptionKeyStatus
from app.repositories.key_rotation_history import KeyRotationHistoryRepository
from tests.conftest import build_encryption_key_service


async def test_get_or_create_active_mints_first_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    key = await keys.get_or_create_active(org_id)
    assert key.version == 1
    assert key.status == EncryptionKeyStatus.ACTIVE
    assert key.organization_id == org_id


async def test_get_or_create_active_reuses_existing_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    first = await keys.get_or_create_active(org_id)
    second = await keys.get_or_create_active(org_id)
    assert first.id == second.id


async def test_keys_are_isolated_per_organization(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    key_a = await keys.get_or_create_active(uuid.uuid4())
    key_b = await keys.get_or_create_active(uuid.uuid4())
    assert key_a.wrapped_key != key_b.wrapped_key


async def test_encrypt_decrypt_round_trips(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    ciphertext, key = await keys.encrypt(org_id, "top-secret-value")
    assert ciphertext != "top-secret-value"
    assert keys.decrypt(ciphertext, key) == "top-secret-value"


async def test_rotate_mints_new_active_key_and_retires_previous(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    original = await keys.get_or_create_active(org_id)

    previous, new_key = await keys.rotate(org_id, rotated_by=None)

    assert previous is not None
    assert previous.id == original.id
    assert previous.status == EncryptionKeyStatus.ROTATED
    assert new_key.status == EncryptionKeyStatus.ACTIVE
    assert new_key.version == original.version + 1

    active = await keys.get_or_create_active(org_id)
    assert active.id == new_key.id


async def test_rotate_with_no_prior_key_returns_none_as_previous(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    previous, new_key = await keys.rotate(uuid.uuid4(), rotated_by=None)
    assert previous is None
    assert new_key.version == 1


async def test_rotate_records_history(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    await keys.get_or_create_active(org_id)
    _previous, new_key = await keys.rotate(org_id, rotated_by=None, reason="scheduled")

    history = await KeyRotationHistoryRepository(db_session).list_all()
    matching = [entry for entry in history if entry.encryption_key_id == new_key.id]
    assert len(matching) == 1
    assert matching[0].reason == "scheduled"


async def test_revoke_marks_key_revoked(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    key = await keys.get_or_create_active(uuid.uuid4())
    revoked = await keys.revoke(key.id)
    assert revoked.status == EncryptionKeyStatus.REVOKED


async def test_revoke_raises_when_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await keys.revoke(uuid.uuid4())


async def test_reencrypt_preserves_plaintext_under_new_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    org_id = uuid.uuid4()
    ciphertext, old_key = await keys.encrypt(org_id, "migrate-this")
    _previous, new_key = await keys.rotate(org_id, rotated_by=None)

    reencrypted = keys.reencrypt(ciphertext, old_key=old_key, new_key=new_key)
    assert keys.decrypt(reencrypted, new_key) == "migrate-this"
    with pytest.raises(InvalidTag):
        keys.decrypt(reencrypted, old_key)


async def test_get_by_id_raises_when_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    keys = build_encryption_key_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await keys.get_by_id(uuid.uuid4())


async def test_mint_publishes_key_generated_event(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    captured: list[object] = []

    async def _publish(event: object) -> None:
        captured.append(event)

    keys = build_encryption_key_service(db_session, envelope, publish_event=_publish)
    await keys.get_or_create_active(uuid.uuid4())

    assert any(isinstance(event, KeyGeneratedEvent) for event in captured)


async def test_revoke_publishes_key_revoked_event(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    captured: list[object] = []

    async def _publish(event: object) -> None:
        captured.append(event)

    keys = build_encryption_key_service(db_session, envelope, publish_event=_publish)
    key = await keys.get_or_create_active(uuid.uuid4())
    captured.clear()
    await keys.revoke(key.id)

    assert any(isinstance(event, KeyRevokedEvent) for event in captured)
