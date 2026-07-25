"""Tests for :class:`app.services.tosca.ConfigurationToscaService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ToscaComponentType
from app.repositories.configuration_tosca_template import ConfigurationToscaTemplateRepository
from app.services.tosca import ConfigurationToscaService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationToscaService:
    return ConfigurationToscaService(ConfigurationToscaTemplateRepository(db_session))


async def test_create_valid_service_template(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    template = await service.create(
        organization_id=org_id,
        project_id=None,
        profile_id=None,
        component_type=ToscaComponentType.SERVICE_TEMPLATE,
        name="web-app-topology",
        content={
            "tosca_definitions_version": "tosca_simple_yaml_1_3",
            "topology_template": {"node_templates": {}},
        },
        csar_url=None,
    )

    fetched = await service.get_by_id(template.id)
    assert fetched.name == "web-app-topology"


async def test_create_invalid_content_raises_validation_error(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(ValidationError):
        await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            profile_id=None,
            component_type=ToscaComponentType.NODE_TEMPLATE,
            name="incomplete-node",
            content={},
            csar_url=None,
        )


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_profile_and_delete(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    template = await service.create(
        organization_id=profile.organization_id,
        project_id=None,
        profile_id=profile.id,
        component_type=ToscaComponentType.NODE_TEMPLATE,
        name="node-a",
        content={"type": "tosca.nodes.Compute"},
        csar_url=None,
    )

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1

    await service.delete(template.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(template.id)
