"""Direct service-layer tests for secrets-management sub-resources
docs/035 never names a REST endpoint for: metadata, categories, tags
(management beyond secret-creation-time assignment, already covered in
``test_service_secret.py``), credential sets, and tokens -- plus
``audit``/``rotation_history``/``key_rotation_history``, which do have
callers (``SecretService``, ``EncryptionKeyService``) but no router of
their own. Each exists for programmatic completeness only, the same
shape ``services/project-service``'s own
``test_services_no_rest_surface.py`` established.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import AuditOutcome, TokenStatus, TokenType
from app.models.secret_audit import SecretAuditEntry
from app.repositories.credential_set import CredentialSetRepository
from app.repositories.key_rotation_history import KeyRotationHistoryRepository
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_category import SecretCategoryRepository
from app.repositories.secret_metadata import SecretMetadataRepository
from app.repositories.token import TokenRepository
from app.services.category import SecretCategoryService
from app.services.credential_set import CredentialSetService
from app.services.key_rotation_history import KeyRotationHistoryService
from app.services.metadata import SecretMetadataService
from app.services.token import TokenService
from tests.conftest import build_encryption_key_service, make_secret

# --- Metadata ---


async def test_metadata_set_and_list(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretMetadataService(SecretMetadataRepository(db_session))

    entry = await service.set(
        secret.id, organization_id=secret.organization_id, key="environment", value="production"
    )
    assert entry.value == "production"

    entries = await service.list_for_secret(secret.id)
    assert len(entries) == 1


async def test_metadata_set_duplicate_key_conflicts(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretMetadataService(SecretMetadataRepository(db_session))
    await service.set(secret.id, organization_id=secret.organization_id, key="k", value="v1")
    with pytest.raises(ConflictError):
        await service.set(secret.id, organization_id=secret.organization_id, key="k", value="v2")


async def test_metadata_remove(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretMetadataService(SecretMetadataRepository(db_session))
    entry = await service.set(secret.id, organization_id=secret.organization_id, key="k", value="v")
    await service.remove(secret.id, entry.id)
    assert await service.list_for_secret(secret.id) == []


async def test_metadata_remove_wrong_secret_raises(db_session: AsyncSession) -> None:
    secret_a = await make_secret(db_session)
    secret_b = await make_secret(db_session)
    service = SecretMetadataService(SecretMetadataRepository(db_session))
    entry = await service.set(
        secret_a.id, organization_id=secret_a.organization_id, key="k", value="v"
    )
    with pytest.raises(NotFoundError):
        await service.remove(secret_b.id, entry.id)


# --- Categories ---


async def test_category_create_and_list(db_session: AsyncSession) -> None:
    service = SecretCategoryService(SecretCategoryRepository(db_session))
    org_id = uuid.uuid4()
    category = await service.create(organization_id=org_id, name="Database", description="DB creds")
    assert category.name == "Database"

    categories = await service.list_for_org(org_id)
    assert len(categories) == 1


async def test_category_duplicate_name_conflicts(db_session: AsyncSession) -> None:
    service = SecretCategoryService(SecretCategoryRepository(db_session))
    org_id = uuid.uuid4()
    await service.create(organization_id=org_id, name="dup")
    with pytest.raises(ConflictError):
        await service.create(organization_id=org_id, name="dup")


async def test_category_delete(db_session: AsyncSession) -> None:
    service = SecretCategoryService(SecretCategoryRepository(db_session))
    category = await service.create(organization_id=uuid.uuid4(), name="deletable")
    await service.delete(category.id)
    with pytest.raises(NotFoundError):
        await service.delete(category.id)


# --- Credential sets ---


async def test_credential_set_create_and_list(db_session: AsyncSession) -> None:
    service = CredentialSetService(CredentialSetRepository(db_session))
    org_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    credential_set = await service.create(
        organization_id=org_id, name="bundle", secret_ids=[secret_id]
    )
    assert credential_set.secret_ids == [str(secret_id)]

    results = await service.list_for_org(org_id)
    assert len(results) == 1


async def test_credential_set_add_and_remove_secret(db_session: AsyncSession) -> None:
    service = CredentialSetService(CredentialSetRepository(db_session))
    credential_set = await service.create(organization_id=uuid.uuid4(), name="bundle")
    secret_id = uuid.uuid4()

    updated = await service.add_secret(credential_set.id, secret_id)
    assert str(secret_id) in updated.secret_ids

    # Adding the same secret twice must not duplicate it.
    updated_again = await service.add_secret(credential_set.id, secret_id)
    assert updated_again.secret_ids.count(str(secret_id)) == 1

    removed = await service.remove_secret(credential_set.id, secret_id)
    assert str(secret_id) not in removed.secret_ids


async def test_credential_set_delete(db_session: AsyncSession) -> None:
    service = CredentialSetService(CredentialSetRepository(db_session))
    credential_set = await service.create(organization_id=uuid.uuid4(), name="deletable")
    await service.delete(credential_set.id)
    with pytest.raises(NotFoundError):
        await service.delete(credential_set.id)


# --- Key rotation history ---


async def test_key_rotation_history_record_and_list(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = KeyRotationHistoryService(KeyRotationHistoryRepository(db_session))
    org_id = uuid.uuid4()
    key = await build_encryption_key_service(db_session, envelope).get_or_create_active(org_id)

    await service.record(
        organization_id=org_id,
        encryption_key_id=key.id,
        previous_key_id=None,
        rotated_by=None,
        reason="initial",
        secrets_migrated_count=0,
    )
    history = await service.list_all()
    assert any(entry.encryption_key_id == key.id for entry in history)


# --- Tokens ---


async def test_token_register_and_list(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = TokenService(TokenRepository(db_session))

    token = await service.register(
        organization_id=secret.organization_id,
        project_id=None,
        name="oauth-token",
        token_type=TokenType.OAUTH,
        secret_id=secret.id,
    )
    assert token.status == TokenStatus.ACTIVE

    results = await service.list_for_org(secret.organization_id)
    assert len(results) == 1


async def test_token_revoke(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = TokenService(TokenRepository(db_session))
    token = await service.register(
        organization_id=secret.organization_id,
        project_id=None,
        name="revocable-token",
        token_type=TokenType.ACCESS,
        secret_id=secret.id,
    )
    revoked = await service.revoke(token.id)
    assert revoked.status == TokenStatus.REVOKED


async def test_token_revoke_raises_when_missing(db_session: AsyncSession) -> None:
    service = TokenService(TokenRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.revoke(uuid.uuid4())


async def test_token_mark_expired_if_due(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = TokenService(TokenRepository(db_session))
    token = await service.register(
        organization_id=secret.organization_id,
        project_id=None,
        name="expirable-token",
        token_type=TokenType.REFRESH,
        secret_id=secret.id,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await service.mark_expired_if_due(token)
    assert token.status == TokenStatus.EXPIRED


async def test_token_mark_expired_if_due_no_op_when_not_yet_expired(
    db_session: AsyncSession,
) -> None:
    secret = await make_secret(db_session)
    service = TokenService(TokenRepository(db_session))
    token = await service.register(
        organization_id=secret.organization_id,
        project_id=None,
        name="not-yet-expired",
        token_type=TokenType.REFRESH,
        secret_id=secret.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    await service.mark_expired_if_due(token)
    assert token.status == TokenStatus.ACTIVE


# --- Audit / rotation history direct repository access ---


async def test_audit_repository_records_outcome(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    audit = SecretAuditRepository(db_session)

    entry = await audit.create(
        SecretAuditEntry(
            secret_id=secret.id,
            organization_id=secret.organization_id,
            actor_id=None,
            action="provider_access",
            outcome=AuditOutcome.FAILURE,
            reason="provider unreachable",
        )
    )
    assert entry.outcome == AuditOutcome.FAILURE
