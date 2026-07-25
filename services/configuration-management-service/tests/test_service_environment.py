"""Tests for :class:`app.services.environment.ConfigurationEnvironmentService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentType
from app.repositories.configuration_environment import ConfigurationEnvironmentRepository
from app.services.environment import ConfigurationEnvironmentService


def build_service(db_session: AsyncSession) -> ConfigurationEnvironmentService:
    return ConfigurationEnvironmentService(ConfigurationEnvironmentRepository(db_session))


async def test_create_and_get(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    environment = await service.create(
        organization_id=org_id,
        project_id=None,
        name="production-us-east",
        environment_type=EnvironmentType.PRODUCTION,
        description="Primary production environment.",
    )

    fetched = await service.get_by_id(environment.id)
    assert fetched.name == "production-us-east"


async def test_create_rejects_duplicate_name(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        name="staging",
        environment_type=EnvironmentType.STAGING,
        description=None,
    )

    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            project_id=None,
            name="staging",
            environment_type=EnvironmentType.STAGING,
            description=None,
        )


async def test_list_for_org(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        name="dev",
        environment_type=EnvironmentType.DEVELOPMENT,
        description=None,
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        name="qa",
        environment_type=EnvironmentType.QA,
        description=None,
    )

    environments = await service.list_for_org(org_id)
    assert len(environments) == 2


async def test_update_and_delete(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    environment = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="edge-site-1",
        environment_type=EnvironmentType.EDGE,
        description=None,
    )

    updated = await service.update(
        environment.id, environment_type=EnvironmentType.EDGE, description="Updated."
    )
    assert updated.description == "Updated."

    await service.delete(environment.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(environment.id)
