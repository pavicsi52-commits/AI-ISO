"""Direct service-layer tests for ``app/services/secret_version.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.services.encryption_key import EncryptionKeyService
from tests.conftest import build_encryption_key_service, build_secret_version_service, make_secret


async def test_create_version_is_current_and_numbered_one(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)

    version = await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="first", created_by=None
    )
    assert version.version_number == 1
    assert version.is_current is True


async def test_create_version_demotes_previous_current(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)

    first = await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v1", created_by=None
    )
    second = await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v2", created_by=None
    )

    refreshed_first = await versions.get_by_number(secret.id, first.version_number)
    assert refreshed_first.is_current is False
    assert second.is_current is True
    assert second.version_number == first.version_number + 1


async def test_get_current_raises_when_no_version(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await versions.get_current(secret.id)


async def test_get_by_number_raises_when_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v1", created_by=None
    )
    with pytest.raises(NotFoundError):
        await versions.get_by_number(secret.id, 99)


async def test_list_for_secret_orders_newest_first(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v1", created_by=None
    )
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v2", created_by=None
    )
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v3", created_by=None
    )

    history = await versions.list_for_secret(secret.id)
    assert [v.version_number for v in history] == [3, 2, 1]


async def test_rollback_creates_new_version_with_old_plaintext(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="original", created_by=None
    )
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="changed", created_by=None
    )

    rolled_back = await versions.rollback(
        secret.id,
        organization_id=secret.organization_id,
        target_version_number=1,
        rolled_back_by=None,
    )

    assert rolled_back.version_number == 3
    assert rolled_back.is_current is True
    assert await versions.decrypt(rolled_back) == "original"


async def test_rollback_raises_when_target_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    versions = build_secret_version_service(db_session, envelope)
    await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="v1", created_by=None
    )
    with pytest.raises(NotFoundError):
        await versions.rollback(
            secret.id,
            organization_id=secret.organization_id,
            target_version_number=42,
            rolled_back_by=None,
        )


async def test_migrate_key_reencrypts_without_changing_plaintext(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret = await make_secret(db_session)
    keys: EncryptionKeyService = build_encryption_key_service(db_session, envelope)
    versions = build_secret_version_service(db_session, envelope)

    version = await versions.create_version(
        secret.id, organization_id=secret.organization_id, plaintext="migrate-me", created_by=None
    )
    old_key = await keys.get_by_id(version.encryption_key_id)
    old_ciphertext = version.ciphertext

    _previous, new_key = await keys.rotate(secret.organization_id, rotated_by=None)
    migrated_count = await versions.migrate_key(old_key=old_key, new_key=new_key)

    assert migrated_count == 1
    assert version.ciphertext != old_ciphertext
    assert version.encryption_key_id == new_key.id
    assert await versions.decrypt(version) == "migrate-me"


async def test_migrate_key_skips_versions_under_other_keys(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    secret_a = await make_secret(db_session, organization_id=uuid.uuid4())
    keys = build_encryption_key_service(db_session, envelope)
    versions = build_secret_version_service(db_session, envelope)

    await versions.create_version(
        secret_a.id,
        organization_id=secret_a.organization_id,
        plaintext="untouched",
        created_by=None,
    )
    other_org_key = await keys.get_or_create_active(uuid.uuid4())
    unrelated_key = await keys.get_or_create_active(uuid.uuid4())

    migrated_count = await versions.migrate_key(old_key=other_org_key, new_key=unrelated_key)
    assert migrated_count == 0
