"""Tests for :class:`app.services.variable.ConfigurationVariableService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import VariableScope
from app.repositories.configuration_variable import ConfigurationVariableRepository
from app.services.variable import ConfigurationVariableService


def build_service(db_session: AsyncSession) -> ConfigurationVariableService:
    return ConfigurationVariableService(ConfigurationVariableRepository(db_session))


async def test_create_and_get(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()

    variable = await service.create(
        organization_id=org_id,
        project_id=None,
        scope=VariableScope.ORGANIZATION,
        scope_ref_id=None,
        key="max_connections",
        value="100",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )

    fetched = await service.get_by_id(variable.id)
    assert fetched.key == "max_connections"
    assert fetched.value == "100"


async def test_create_rejects_duplicate_key_at_same_scope(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        scope=VariableScope.GLOBAL,
        scope_ref_id=None,
        key="dup",
        value="1",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )

    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            project_id=None,
            scope=VariableScope.GLOBAL,
            scope_ref_id=None,
            key="dup",
            value="2",
            is_secret_reference=False,
            is_computed=False,
            validation_rule=None,
        )


async def test_create_rejects_secret_and_computed_together(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(ValidationError):
        await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            scope=VariableScope.GLOBAL,
            scope_ref_id=None,
            key="bad",
            value=None,
            is_secret_reference=True,
            is_computed=True,
            validation_rule=None,
        )


async def test_list_for_scope(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        project_id=None,
        scope=VariableScope.ORGANIZATION,
        scope_ref_id=None,
        key="a",
        value="1",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )
    await service.create(
        organization_id=org_id,
        project_id=None,
        scope=VariableScope.GLOBAL,
        scope_ref_id=None,
        key="b",
        value="2",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )

    org_scoped = await service.list_for_scope(org_id, VariableScope.ORGANIZATION)
    assert len(org_scoped) == 1
    assert org_scoped[0].key == "a"


async def test_update_and_delete(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    variable = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=VariableScope.RUNTIME,
        scope_ref_id=None,
        key="runtime_key",
        value="old",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )

    updated = await service.update(
        variable.id,
        value="new",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )
    assert updated.value == "new"

    await service.delete(variable.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(variable.id)
