"""Tests for :class:`app.services.statistics.MonitoringStatisticsService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AvailabilityStatus, HealthCheckType, SLAType
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.repositories.monitoring_statistics import MonitoringStatisticsRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService
from app.services.sla import MonitoringSLAService
from app.services.statistics import MonitoringStatisticsService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringStatisticsService:
    return MonitoringStatisticsService(
        MonitoringStatisticsRepository(db_session),
        MonitoringTargetRepository(db_session),
        MonitoringHealthService(MonitoringHealthRepository(db_session)),
        MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session)),
        MonitoringSLARepository(db_session),
        MonitoringSLORepository(db_session),
    )


class TestMonitoringStatisticsService:
    async def test_get_for_org_recomputes_when_no_snapshot_exists(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        service = _service(db_session)
        snapshot = await service.get_for_org(org_id)
        assert snapshot.total_targets == 0
        assert snapshot.average_health_score == 0.0
        assert snapshot.average_availability_percentage == 100.0
        assert snapshot.sla_compliance_percentage == 100.0

    async def test_recompute_reflects_real_state(self, db_session: AsyncSession) -> None:
        target = await make_target(db_session)
        org_id = target.organization_id
        health = MonitoringHealthService(MonitoringHealthRepository(db_session))
        await health.record(
            organization_id=org_id,
            target_id=target.id,
            check_type=HealthCheckType.HEARTBEAT,
            status=HealthStatus.HEALTHY,
        )
        availability = MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session))
        now = datetime.now(UTC)
        await availability.record_status(
            organization_id=org_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
            observed_at=now - timedelta(hours=1),
        )
        await availability.record_status(
            organization_id=org_id, target_id=target.id, status=AvailabilityStatus.DOWN
        )
        sla_service = MonitoringSLAService(MonitoringSLARepository(db_session))
        await sla_service.create(
            organization_id=org_id,
            target_id=target.id,
            sla_type=SLAType.AVAILABILITY,
            objective_percentage=99.0,
            period_start=now - timedelta(days=30),
            period_end=now,
        )

        service = _service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.total_targets == 1
        assert snapshot.average_health_score == 100.0
        assert 0.0 <= snapshot.average_availability_percentage <= 100.0
        assert snapshot.sla_compliance_percentage == 100.0

    async def test_recompute_updates_existing_snapshot(self, db_session: AsyncSession) -> None:
        target = await make_target(db_session)
        org_id = target.organization_id
        service = _service(db_session)
        first = await service.recompute(org_id)
        second = await service.recompute(org_id)
        assert first.id == second.id
