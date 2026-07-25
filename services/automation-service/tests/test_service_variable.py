"""Tests for :class:`app.services.variable.AutomationVariableService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import VariableScope
from app.repositories.automation_variable import AutomationVariableRepository
from app.services.variable import AutomationVariableService


def _build_service(db_session: AsyncSession) -> AutomationVariableService:
    return AutomationVariableService(AutomationVariableRepository(db_session))


class TestAutomationVariableService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        org_id = uuid.uuid4()
        variable = await service.create(
            organization_id=org_id,
            scope=VariableScope.ORGANIZATION,
            scope_ref_id=None,
            key="region",
            value="us-east-1",
            is_secret_reference=False,
        )
        fetched = await service.get_by_id(variable.id)
        assert fetched.key == "region"
        assert fetched.value == "us-east-1"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_create_duplicate_key_raises_conflict(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            scope=VariableScope.GLOBAL,
            scope_ref_id=None,
            key="dup",
            value="a",
            is_secret_reference=False,
        )
        with pytest.raises(ConflictError, match="already defined"):
            await service.create(
                organization_id=org_id,
                scope=VariableScope.GLOBAL,
                scope_ref_id=None,
                key="dup",
                value="b",
                is_secret_reference=False,
            )

    async def test_list_for_scope(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.create(
            organization_id=org_id,
            scope=VariableScope.JOB,
            scope_ref_id=None,
            key="k1",
            value="v1",
            is_secret_reference=False,
        )
        await service.create(
            organization_id=org_id,
            scope=VariableScope.EXECUTION,
            scope_ref_id=None,
            key="k2",
            value="v2",
            is_secret_reference=False,
        )
        job_scoped = await service.list_for_scope(org_id, VariableScope.JOB)
        assert len(job_scoped) == 1
        assert job_scoped[0].key == "k1"

    async def test_update_changes_value(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        variable = await service.create(
            organization_id=uuid.uuid4(),
            scope=VariableScope.GLOBAL,
            scope_ref_id=None,
            key="k",
            value="old",
            is_secret_reference=False,
        )
        updated = await service.update(variable.id, value="new", is_secret_reference=True)
        assert updated.value == "new"
        assert updated.is_secret_reference is True

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        variable = await service.create(
            organization_id=uuid.uuid4(),
            scope=VariableScope.GLOBAL,
            scope_ref_id=None,
            key="k",
            value="v",
            is_secret_reference=False,
        )
        await service.delete(variable.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(variable.id)
