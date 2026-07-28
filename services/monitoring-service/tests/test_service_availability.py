"""Tests for :class:`app.services.availability.MonitoringAvailabilityService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AvailabilityStatus
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.services.availability import MonitoringAvailabilityService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringAvailabilityService:
    return MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session))


class TestMonitoringAvailabilityService:
    async def test_record_status_opens_new_interval(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        interval = await service.record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
        )
        assert interval.status == AvailabilityStatus.UP
        assert interval.ended_at is None
        current = await service.get_current_for_target(target.id)
        assert current is not None
        assert current.id == interval.id

    async def test_record_status_same_status_is_noop(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        first = await service.record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
        )
        second = await service.record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
        )
        assert second.id == first.id

    async def test_record_status_change_closes_prior_interval(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        started_at = datetime.now(UTC) - timedelta(minutes=5)
        first = await service.record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
            observed_at=started_at,
        )
        second = await service.record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.DOWN,
        )
        assert second.id != first.id
        intervals = await service.list_for_target(target.id)
        closed = next(i for i in intervals if i.id == first.id)
        assert closed.ended_at is not None
        assert closed.duration_seconds is not None
        assert closed.duration_seconds > 0

    async def test_get_current_for_target_returns_none_when_no_interval(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        assert await service.get_current_for_target(uuid.uuid4()) is None
