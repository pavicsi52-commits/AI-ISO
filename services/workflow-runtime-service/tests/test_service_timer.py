"""Tests for :class:`app.services.timer.WorkflowTimerService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TimerType
from app.repositories.workflow_timer import WorkflowTimerRepository
from app.services.timer import WorkflowTimerService
from tests.conftest import make_definition


def _build_service(db_session: AsyncSession) -> WorkflowTimerService:
    return WorkflowTimerService(WorkflowTimerRepository(db_session))


class TestWorkflowTimerService:
    async def test_create_cron_timer(self, db_session: AsyncSession) -> None:
        definition = await make_definition(db_session)
        service = _build_service(db_session)
        timer = await service.create(
            organization_id=definition.organization_id,
            definition_id=definition.id,
            timer_type=TimerType.CRON,
            cron_expression="0 * * * *",
        )
        assert timer.timer_type == TimerType.CRON
        assert timer.fired is False

    async def test_list_for_definition(self, db_session: AsyncSession) -> None:
        definition = await make_definition(db_session)
        service = _build_service(db_session)
        await service.create(
            organization_id=definition.organization_id,
            definition_id=definition.id,
            timer_type=TimerType.DELAY,
        )
        timers = await service.list_for_definition(definition.id)
        assert len(timers) == 1

    async def test_list_all_schedulable_filters_by_type_and_cron_expression(
        self, db_session: AsyncSession
    ) -> None:
        service = _build_service(db_session)
        cron_definition = await make_definition(db_session)
        recurring_definition = await make_definition(db_session)
        delay_definition = await make_definition(db_session)
        bare_cron_definition = await make_definition(db_session)
        await service.create(
            organization_id=cron_definition.organization_id,
            definition_id=cron_definition.id,
            timer_type=TimerType.CRON,
            cron_expression="0 * * * *",
        )
        await service.create(
            organization_id=recurring_definition.organization_id,
            definition_id=recurring_definition.id,
            timer_type=TimerType.RECURRING,
            cron_expression="*/5 * * * *",
        )
        await service.create(
            organization_id=delay_definition.organization_id,
            definition_id=delay_definition.id,
            timer_type=TimerType.DELAY,
        )
        await service.create(
            organization_id=bare_cron_definition.organization_id,
            definition_id=bare_cron_definition.id,
            timer_type=TimerType.CRON,
            cron_expression=None,
        )
        schedulable = await service.list_all_schedulable()
        assert len(schedulable) == 2

    async def test_list_due(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        past_definition = await make_definition(db_session)
        future_definition = await make_definition(db_session)
        past = datetime.now(UTC) - timedelta(minutes=1)
        future = datetime.now(UTC) + timedelta(hours=1)
        await service.create(
            organization_id=past_definition.organization_id,
            definition_id=past_definition.id,
            timer_type=TimerType.TIMEOUT,
            fires_at=past,
        )
        await service.create(
            organization_id=future_definition.organization_id,
            definition_id=future_definition.id,
            timer_type=TimerType.TIMEOUT,
            fires_at=future,
        )
        due = await service.list_due(before=datetime.now(UTC))
        assert len(due) == 1

    async def test_mark_fired(self, db_session: AsyncSession) -> None:
        definition = await make_definition(db_session)
        service = _build_service(db_session)
        timer = await service.create(
            organization_id=definition.organization_id,
            definition_id=definition.id,
            timer_type=TimerType.DELAY,
        )
        fired = await service.mark_fired(timer.id)
        assert fired.fired is True

    async def test_mark_fired_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.mark_fired(uuid.uuid4())
