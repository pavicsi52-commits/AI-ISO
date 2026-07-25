"""Tests for :class:`app.services.execution_plan.AutomationExecutionPlanService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.automation_execution_plan import AutomationExecutionPlanRepository
from app.services.execution_plan import AutomationExecutionPlanService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationExecutionPlanService:
    return AutomationExecutionPlanService(AutomationExecutionPlanRepository(db_session))


class TestAutomationExecutionPlanService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        plan = await service.create(
            organization_id=job.organization_id,
            job_id=job.id,
            name="standard-rollout",
            steps=[{"phase": "pre_check"}, {"phase": "execute"}],
            approval_gates=[{"level": 1}],
            rollback_plan={"type": "automatic"},
        )
        fetched = await service.get_by_id(plan.id)
        assert fetched.name == "standard-rollout"
        assert len(fetched.steps) == 2

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.create(
            organization_id=org_id,
            job_id=None,
            name="p1",
            steps=[],
            approval_gates=[],
            rollback_plan=None,
        )
        plans = await service.list_for_org(org_id)
        assert len(plans) == 1

    async def test_list_for_job(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.create(
            organization_id=job.organization_id,
            job_id=job.id,
            name="p1",
            steps=[],
            approval_gates=[],
            rollback_plan=None,
        )
        plans = await service.list_for_job(job.id)
        assert len(plans) == 1

    async def test_update(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        plan = await service.create(
            organization_id=uuid.uuid4(),
            job_id=None,
            name="original",
            steps=[],
            approval_gates=[],
            rollback_plan=None,
        )
        updated = await service.update(
            plan.id,
            name="renamed",
            steps=[{"phase": "cleanup"}],
            approval_gates=[],
            rollback_plan={"type": "manual"},
        )
        assert updated.name == "renamed"
        assert updated.steps == [{"phase": "cleanup"}]

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        plan = await service.create(
            organization_id=uuid.uuid4(),
            job_id=None,
            name="p1",
            steps=[],
            approval_gates=[],
            rollback_plan=None,
        )
        await service.delete(plan.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(plan.id)
