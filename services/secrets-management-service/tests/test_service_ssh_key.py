"""Direct service-layer tests for ``app/services/ssh_key.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import SSHKeyStatus, SSHKeyType
from app.repositories.ssh_key import SSHKeyRepository
from app.services.ssh_key import SSHKeyService
from app.ssh.keygen import compute_fingerprint, generate_ssh_keypair
from tests.conftest import build_secret_service


def _ssh_service(db_session: AsyncSession, envelope: EnvelopeEncryption) -> SSHKeyService:
    secrets = build_secret_service(db_session, envelope)
    return SSHKeyService(SSHKeyRepository(db_session), secrets)


async def test_create_generates_keypair_when_none_supplied(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    owner_id = uuid.uuid4()

    ssh_key, private_key = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="generated-key",
        key_type=SSHKeyType.ED25519,
        owner_id=owner_id,
        expires_at=None,
        public_key=None,
        private_key=None,
    )
    assert ssh_key.status == SSHKeyStatus.ACTIVE
    assert ssh_key.public_key.startswith("ssh-ed25519")
    assert private_key.startswith("-----BEGIN PRIVATE KEY-----")
    assert ssh_key.fingerprint == compute_fingerprint(ssh_key.public_key)


async def test_create_stores_private_key_as_secret(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    owner_id = uuid.uuid4()

    ssh_key, private_key = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="secret-backed-key",
        key_type=SSHKeyType.ED25519,
        owner_id=owner_id,
        expires_at=None,
        public_key=None,
        private_key=None,
    )
    secrets = build_secret_service(db_session, envelope)
    _secret, stored_value = await secrets.get_decrypted(
        ssh_key.private_key_secret_id, actor_id=owner_id
    )
    assert stored_value == private_key


async def test_create_import_mode_uses_supplied_keypair(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    private_pem, public_openssh = generate_ssh_keypair(SSHKeyType.RSA)

    ssh_key, returned_private = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="imported-key",
        key_type=SSHKeyType.RSA,
        owner_id=uuid.uuid4(),
        expires_at=None,
        public_key=public_openssh,
        private_key=private_pem,
    )
    assert ssh_key.public_key == public_openssh
    assert returned_private == private_pem


async def test_create_duplicate_fingerprint_conflicts(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    private_pem, public_openssh = generate_ssh_keypair(SSHKeyType.RSA)
    org_id = uuid.uuid4()

    await service.create(
        organization_id=org_id,
        project_id=None,
        name="first",
        key_type=SSHKeyType.RSA,
        owner_id=uuid.uuid4(),
        expires_at=None,
        public_key=public_openssh,
        private_key=private_pem,
    )
    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            project_id=None,
            name="second",
            key_type=SSHKeyType.RSA,
            owner_id=uuid.uuid4(),
            expires_at=None,
            public_key=public_openssh,
            private_key=private_pem,
        )


async def test_list_for_org_scopes_correctly(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    org_a = uuid.uuid4()
    await service.create(
        organization_id=org_a,
        project_id=None,
        name="org-a-key",
        key_type=SSHKeyType.ED25519,
        owner_id=uuid.uuid4(),
        expires_at=None,
        public_key=None,
        private_key=None,
    )
    await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="org-b-key",
        key_type=SSHKeyType.ED25519,
        owner_id=uuid.uuid4(),
        expires_at=None,
        public_key=None,
        private_key=None,
    )
    results = await service.list_for_org(org_a)
    assert len(results) == 1
    assert results[0].name == "org-a-key"


async def test_delete_removes_ssh_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _ssh_service(db_session, envelope)
    ssh_key, _private = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="deletable",
        key_type=SSHKeyType.ED25519,
        owner_id=uuid.uuid4(),
        expires_at=None,
        public_key=None,
        private_key=None,
    )
    await service.delete(ssh_key.id)
    with pytest.raises(NotFoundError):
        await SSHKeyRepository(db_session).require_by_id(ssh_key.id)
