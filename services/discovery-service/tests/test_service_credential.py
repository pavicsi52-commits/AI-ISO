"""Tests for :class:`app.services.credential.DiscoveryCredentialService`
against a real (SAVEPOINT-isolated) Postgres session.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CredentialType, ProtocolType
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.schemas.scan import InlineCredentialSpec
from app.services.credential import DiscoveryCredentialService


def _service(session: AsyncSession) -> DiscoveryCredentialService:
    return DiscoveryCredentialService(DiscoveryCredentialRepository(session))


async def test_create_from_spec(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    spec = InlineCredentialSpec(
        secret_id=secret_id,
        credential_type=CredentialType.PASSWORD,
        name="ssh-cred",
        username="admin",
    )
    credential = await service.create_from_spec(
        spec, organization_id=org_id, protocol=ProtocolType.SSH
    )
    assert credential.id is not None
    assert credential.secret_id == secret_id
    assert credential.username == "admin"
    assert credential.credential_type == CredentialType.PASSWORD
    assert credential.protocol == ProtocolType.SSH

    found = await service.get_by_id(credential.id)
    assert found.name == "ssh-cred"


async def test_create_from_spec_reuses_existing_same_name_credential(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    spec = InlineCredentialSpec(
        secret_id=uuid.uuid4(),
        credential_type=CredentialType.API_KEY,
        name="reused-cred",
    )
    first = await service.create_from_spec(spec, organization_id=org_id, protocol=ProtocolType.HTTP)
    second = await service.create_from_spec(
        spec, organization_id=org_id, protocol=ProtocolType.HTTP
    )
    assert first.id == second.id


async def test_get_by_id_unknown_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())
