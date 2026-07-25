"""Tests for :class:`app.services.schedule.AutomationScheduleService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.automation_schedule import AutomationScheduleRepository
from app.services.schedule import AutomationScheduleService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationScheduleService:
    return AutomationScheduleService(AutomationScheduleRepository(db_session))


class TestAutomationScheduleService:
    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        schedule = await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 3 * * *", enabled=True
        )
        fetched = await service.get_by_id(schedule.id)
        assert fetched.cron_expression == "0 3 * * *"

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_job(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.create(
            job.id, organization_id=job.organization_id, cron_expression="* * * * *", enabled=True
        )
        schedules = await service.list_for_job(job.id)
        assert len(schedules) == 1

    async def test_list_enabled_for_org_excludes_disabled(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 * * * *", enabled=True
        )
        await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 0 * * *", enabled=False
        )
        enabled = await service.list_enabled_for_org(job.organization_id)
        assert len(enabled) == 1
        assert enabled[0].enabled is True

    async def test_set_enabled(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        schedule = await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 * * * *", enabled=True
        )
        disabled = await service.set_enabled(schedule.id, enabled=False)
        assert disabled.enabled is False

    async def test_record_run_updates_timestamps(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        schedule = await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 * * * *", enabled=True
        )
        now = datetime.now(UTC)
        updated = await service.record_run(schedule.id, ran_at=now, next_run_at=None)
        assert updated.last_run_at == now
        assert updated.next_run_at is None

    async def test_delete(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        schedule = await service.create(
            job.id, organization_id=job.organization_id, cron_expression="0 * * * *", enabled=True
        )
        await service.delete(schedule.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(schedule.id)
