"""Tests for :class:`app.services.template.ConfigurationTemplateService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConfigurationType
from app.repositories.configuration_template import ConfigurationTemplateRepository
from app.services.template import ConfigurationTemplateService


def build_service(db_session: AsyncSession) -> ConfigurationTemplateService:
    return ConfigurationTemplateService(ConfigurationTemplateRepository(db_session))


async def test_create_and_get(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    template = await service.create(
        organization_id=org_id,
        project_id=None,
        template_name="nginx-base",
        description="Base nginx config.",
        configuration_type=ConfigurationType.APPLICATION,
        content="server { listen 80; }",
        variables_schema={"port": {"type": "integer"}},
    )

    fetched = await service.get_by_id(template.id)
    assert fetched.template_name == "nginx-base"
    assert fetched.configuration_type == ConfigurationType.APPLICATION


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_org_filters_by_configuration_type(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        template_name="app-template",
        description=None,
        configuration_type=ConfigurationType.APPLICATION,
        content="x",
        variables_schema={},
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        template_name="db-template",
        description=None,
        configuration_type=ConfigurationType.DATABASE,
        content="y",
        variables_schema={},
    )

    all_templates = await service.list_for_org(org_id)
    assert len(all_templates) == 2

    db_templates = await service.list_for_org(org_id, configuration_type=ConfigurationType.DATABASE)
    assert len(db_templates) == 1
    assert db_templates[0].template_name == "db-template"


async def test_update_replaces_fields(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    template = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        template_name="original",
        description=None,
        configuration_type=ConfigurationType.APPLICATION,
        content="a",
        variables_schema={},
    )

    updated = await service.update(
        template.id,
        template_name="original",
        description="updated description",
        configuration_type=ConfigurationType.APPLICATION,
        content="b",
        variables_schema={"x": "y"},
    )

    assert updated.description == "updated description"
    assert updated.content == "b"


async def test_delete_soft_deletes(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    template = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        template_name="to-delete",
        description=None,
        configuration_type=ConfigurationType.APPLICATION,
        content="a",
        variables_schema={},
    )

    await service.delete(template.id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(template.id)
