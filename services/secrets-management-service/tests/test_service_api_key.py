"""Direct service-layer tests for ``app/services/api_key.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.apikey import generate_api_key
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import ApiKeyStatus
from app.repositories.api_key import ApiKeyRepository
from app.services.api_key import ApiKeyService
from tests.conftest import build_secret_service


def _api_key_service(db_session: AsyncSession, envelope: EnvelopeEncryption) -> ApiKeyService:
    secrets = build_secret_service(db_session, envelope)
    return ApiKeyService(ApiKeyRepository(db_session), secrets)


async def test_create_generates_value_when_none_supplied(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    owner_id = uuid.uuid4()

    api_key, value = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="openai-key",
        owner_id=owner_id,
        scopes=["chat"],
        expires_at=None,
        value=None,
    )
    assert api_key.status == ApiKeyStatus.ACTIVE
    assert value.startswith("aiios_")
    assert api_key.key_prefix == value[:12]
    assert api_key.scopes == ["chat"]


async def test_create_import_mode_uses_supplied_value(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    supplied_value = generate_api_key()

    api_key, returned_value = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="imported-key",
        owner_id=uuid.uuid4(),
        scopes=[],
        expires_at=None,
        value=supplied_value,
    )
    assert returned_value == supplied_value
    assert api_key.key_prefix == supplied_value[:12]


async def test_create_stores_value_as_secret(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    owner_id = uuid.uuid4()

    api_key, value = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="secret-backed-key",
        owner_id=owner_id,
        scopes=[],
        expires_at=None,
        value=None,
    )
    secrets = build_secret_service(db_session, envelope)
    _secret, stored_value = await secrets.get_decrypted(api_key.secret_id, actor_id=owner_id)
    assert stored_value == value


async def test_mark_used_sets_last_used_at(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    api_key, _value = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="tracked-key",
        owner_id=uuid.uuid4(),
        scopes=[],
        expires_at=None,
        value=None,
    )
    assert api_key.last_used_at is None
    updated = await service.mark_used(api_key.id)
    assert updated.last_used_at is not None


async def test_mark_used_raises_when_missing(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    with pytest.raises(NotFoundError):
        await service.mark_used(uuid.uuid4())


async def test_list_for_org_scopes_correctly(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    org_a = uuid.uuid4()
    await service.create(
        organization_id=org_a,
        project_id=None,
        name="org-a-key",
        owner_id=uuid.uuid4(),
        scopes=[],
        expires_at=None,
        value=None,
    )
    await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="org-b-key",
        owner_id=uuid.uuid4(),
        scopes=[],
        expires_at=None,
        value=None,
    )
    results = await service.list_for_org(org_a)
    assert len(results) == 1
    assert results[0].name == "org-a-key"


async def test_delete_removes_api_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _api_key_service(db_session, envelope)
    api_key, _value = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="deletable",
        owner_id=uuid.uuid4(),
        scopes=[],
        expires_at=None,
        value=None,
    )
    await service.delete(api_key.id)
    with pytest.raises(NotFoundError):
        await ApiKeyRepository(db_session).require_by_id(api_key.id)
