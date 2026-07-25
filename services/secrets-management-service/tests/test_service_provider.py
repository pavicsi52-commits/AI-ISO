"""Direct service-layer tests for ``app/services/provider.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProviderType
from app.repositories.secret_provider import SecretProviderRepository
from app.services.provider import SecretProviderService


def _provider_service(db_session: AsyncSession) -> SecretProviderService:
    return SecretProviderService(SecretProviderRepository(db_session))


async def test_create_provider(db_session: AsyncSession) -> None:
    service = _provider_service(db_session)
    provider = await service.create(
        organization_id=uuid.uuid4(),
        name="internal-vault",
        provider_type=ProviderType.INTERNAL_VAULT,
        config={},
        connection_secret_id=None,
        is_enabled=True,
    )
    assert provider.provider_type == ProviderType.INTERNAL_VAULT
    assert provider.is_enabled is True


async def test_create_duplicate_name_conflicts(db_session: AsyncSession) -> None:
    service = _provider_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        name="hashicorp",
        provider_type=ProviderType.HASHICORP_VAULT,
        config={},
        connection_secret_id=None,
        is_enabled=True,
    )
    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            name="hashicorp",
            provider_type=ProviderType.HASHICORP_VAULT,
            config={},
            connection_secret_id=None,
            is_enabled=True,
        )


async def test_list_for_org_scopes_correctly(db_session: AsyncSession) -> None:
    service = _provider_service(db_session)
    org_a = uuid.uuid4()
    await service.create(
        organization_id=org_a,
        name="org-a-provider",
        provider_type=ProviderType.AWS_SECRETS_MANAGER,
        config={},
        connection_secret_id=None,
        is_enabled=True,
    )
    await service.create(
        organization_id=uuid.uuid4(),
        name="org-b-provider",
        provider_type=ProviderType.AZURE_KEY_VAULT,
        config={},
        connection_secret_id=None,
        is_enabled=True,
    )
    results = await service.list_for_org(org_a)
    assert len(results) == 1
    assert results[0].name == "org-a-provider"
