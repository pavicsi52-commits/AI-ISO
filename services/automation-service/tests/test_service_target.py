"""Tests for :class:`app.services.target.AutomationTargetService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConnectorType, ExecutionTargetType
from app.repositories.automation_target import AutomationTargetRepository
from app.services.target import AutomationTargetService
from tests.conftest import make_target


def _build_service(db_session: AsyncSession) -> AutomationTargetService:
    return AutomationTargetService(AutomationTargetRepository(db_session))


class TestAutomationTargetService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        org_id = uuid.uuid4()
        target = await service.create(
            organization_id=org_id,
            project_id=None,
            name="web-1",
            target_type=ExecutionTargetType.VIRTUAL_MACHINE,
            connector_type=ConnectorType.SSH,
            address="10.0.0.5",
            port=22,
            username="deploy",
            credential_ref="secret-1",
            inventory_asset_id=None,
            labels={"tier": "web"},
            tags=["prod"],
            metadata={"owner": "platform"},
        )
        fetched = await service.get_by_id(target.id)
        assert fetched.name == "web-1"
        assert fetched.metadata_ == {"owner": "platform"}

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await make_target(db_session, organization_id=org_id, name="t1")
        await make_target(db_session, organization_id=org_id, name="t2")
        service = _build_service(db_session)
        targets = await service.list_for_org(org_id)
        assert {t.name for t in targets} == {"t1", "t2"}

    async def test_list_for_org_filters_by_target_type(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await make_target(
            db_session, organization_id=org_id, target_type=ExecutionTargetType.PHYSICAL_SERVER
        )
        await make_target(
            db_session, organization_id=org_id, target_type=ExecutionTargetType.KUBERNETES
        )
        service = _build_service(db_session)
        results = await service.list_for_org(org_id, target_type=ExecutionTargetType.KUBERNETES)
        assert len(results) == 1
        assert results[0].target_type == ExecutionTargetType.KUBERNETES

    async def test_list_by_ids(self, db_session: AsyncSession) -> None:
        target1 = await make_target(db_session)
        target2 = await make_target(db_session)
        service = _build_service(db_session)
        results = await service.list_by_ids([target1.id, target2.id])
        assert {t.id for t in results} == {target1.id, target2.id}

    async def test_delete(self, db_session: AsyncSession) -> None:
        target = await make_target(db_session)
        service = _build_service(db_session)
        await service.delete(target.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(target.id)
