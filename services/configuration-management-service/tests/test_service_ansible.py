"""Tests for :class:`app.services.ansible.ConfigurationAnsibleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.configuration_ansible_inventory import (
    ConfigurationAnsibleInventoryRepository,
)
from app.services.ansible import ConfigurationAnsibleService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationAnsibleService:
    return ConfigurationAnsibleService(ConfigurationAnsibleInventoryRepository(db_session))


async def test_create_valid_inventory(db_session: AsyncSession) -> None:
    service = build_service(db_session)

    inventory = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        name="web-servers",
        inventory_content={"webservers": {"hosts": ["web1", "web2"]}},
        host_vars={"web1": {"ansible_user": "deploy"}},
        group_vars={"webservers": {"http_port": 80}},
        playbooks=["site.yml"],
        roles=["nginx"],
        collections=["community.general"],
        vault_ref=None,
    )

    fetched = await service.get_by_id(inventory.id)
    assert fetched.name == "web-servers"


async def test_create_invalid_inventory_raises_validation_error(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(ValidationError):
        await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            profile_id=None,
            name="bad-inventory",
            inventory_content={"webservers": {"hosts": "not-a-list"}},
            host_vars={},
            group_vars={},
            playbooks=["not-yaml.txt"],
            roles=[],
            collections=[],
            vault_ref=None,
        )


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_profile_and_delete(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    inventory = await service.create(
        organization_id=profile.organization_id,
        project_id=None,
        profile_id=profile.id,
        name="db-servers",
        inventory_content={"dbservers": {"hosts": ["db1"]}},
        host_vars={},
        group_vars={},
        playbooks=[],
        roles=[],
        collections=[],
        vault_ref="secret-ref-1",
    )

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1

    await service.delete(inventory.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(inventory.id)
