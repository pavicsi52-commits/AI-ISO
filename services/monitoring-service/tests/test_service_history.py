"""Tests for :class:`app.services.history.MonitoringHistoryService`."""

from __future__ import annotations

from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.monitoring_history import MonitoringHistoryRepository
from app.services.history import MonitoringHistoryService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringHistoryService:
    return MonitoringHistoryService(MonitoringHistoryRepository(db_session))


class TestMonitoringHistoryService:
    async def test_record_and_list_for_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            status=HealthStatus.HEALTHY,
            score=95.0,
        )
        records = await service.list_for_target(target.id)
        assert len(records) == 1
        assert records[0].score == 95.0

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            status=HealthStatus.DEGRADED,
            score=None,
        )
        records = await service.list_for_org(target.organization_id)
        assert len(records) == 1
