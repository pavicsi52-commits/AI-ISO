"""Tests for :class:`app.services.health.MonitoringHealthService`."""

from __future__ import annotations

import uuid

from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import HealthCheckType
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.services.health import MonitoringHealthService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringHealthService:
    return MonitoringHealthService(MonitoringHealthRepository(db_session))


class TestMonitoringHealthService:
    async def test_record_and_get_latest(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.HEARTBEAT,
            status=HealthStatus.HEALTHY,
        )
        latest = await service.get_latest_for_target(target.id)
        assert latest is not None
        assert latest.status == HealthStatus.HEALTHY

    async def test_get_latest_returns_none_when_empty(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        assert await service.get_latest_for_target(uuid.uuid4()) is None

    async def test_list_for_target(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.HEARTBEAT,
            status=HealthStatus.HEALTHY,
        )
        results = await service.list_for_target(target.id)
        assert len(results) == 1

    async def test_compute_overall_for_target_rolls_up_worst_per_type(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.HEARTBEAT,
            status=HealthStatus.HEALTHY,
        )
        await service.record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.COMPONENT_HEALTH,
            status=HealthStatus.UNHEALTHY,
        )
        overall = await service.compute_overall_for_target(target.id)
        assert overall == HealthStatus.UNHEALTHY

    async def test_compute_overall_for_target_no_results_is_unknown(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        overall = await service.compute_overall_for_target(uuid.uuid4())
        assert overall == HealthStatus.UNKNOWN
