"""Tests for :class:`app.services.report.MonitoringReportService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MonitoringReportType
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_history import MonitoringHistoryRepository
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.repositories.monitoring_report import MonitoringReportRepository
from app.repositories.monitoring_sla import MonitoringSLARepository
from app.repositories.monitoring_slo import MonitoringSLORepository
from app.repositories.monitoring_statistics import MonitoringStatisticsRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService
from app.services.history import MonitoringHistoryService
from app.services.performance import MonitoringPerformanceService
from app.services.report import MonitoringReportService
from app.services.statistics import MonitoringStatisticsService
from tests.conftest import make_target


def _service(db_session: AsyncSession) -> MonitoringReportService:
    return MonitoringReportService(
        MonitoringReportRepository(db_session),
        MonitoringHealthService(MonitoringHealthRepository(db_session)),
        MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session)),
        MonitoringPerformanceService(
            MonitoringMetricSeriesRepository(db_session), MonitoringMetricRepository(db_session)
        ),
        MonitoringHistoryService(MonitoringHistoryRepository(db_session)),
        MonitoringStatisticsService(
            MonitoringStatisticsRepository(db_session),
            MonitoringTargetRepository(db_session),
            MonitoringHealthService(MonitoringHealthRepository(db_session)),
            MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session)),
            MonitoringSLARepository(db_session),
            MonitoringSLORepository(db_session),
        ),
        MonitoringSLARepository(db_session),
        MonitoringSLORepository(db_session),
    )


class TestMonitoringReportService:
    @pytest.mark.parametrize(
        "report_type",
        [
            MonitoringReportType.HEALTH,
            MonitoringReportType.AVAILABILITY,
            MonitoringReportType.PERFORMANCE,
            MonitoringReportType.HISTORICAL,
        ],
    )
    async def test_target_scoped_report_types(
        self, db_session: AsyncSession, report_type: MonitoringReportType
    ) -> None:
        target = await make_target(db_session)
        service = _service(db_session)
        report = await service.generate(
            target.organization_id,
            report_type=report_type,
            target_id=target.id,
            parameters={},
            generated_by=None,
        )
        assert report.report_type == report_type
        assert report.target_id == target.id

    @pytest.mark.parametrize(
        "report_type",
        [
            MonitoringReportType.CAPACITY,
            MonitoringReportType.EXECUTIVE,
            MonitoringReportType.SLA,
            MonitoringReportType.SLO,
        ],
    )
    async def test_org_scoped_report_types(
        self, db_session: AsyncSession, report_type: MonitoringReportType
    ) -> None:
        target = await make_target(db_session)
        service = _service(db_session)
        report = await service.generate(
            target.organization_id,
            report_type=report_type,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.report_type == report_type
        assert report.target_id is None

    async def test_target_scoped_without_target_id_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(ValidationError, match="target_id"):
            await service.generate(
                uuid.uuid4(),
                report_type=MonitoringReportType.HEALTH,
                target_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        target = await make_target(db_session)
        service = _service(db_session)
        await service.generate(
            target.organization_id,
            report_type=MonitoringReportType.HEALTH,
            target_id=target.id,
            parameters={},
            generated_by=None,
        )
        reports = await service.list_for_org(target.organization_id)
        assert len(reports) == 1
