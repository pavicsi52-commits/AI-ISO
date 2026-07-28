"""Tests for :class:`app.services.performance.MonitoringPerformanceService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MetricType
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.services.metric_series import MonitoringMetricSeriesService
from app.services.performance import MonitoringPerformanceService
from tests.conftest import make_metric, make_target


def _service(db_session: AsyncSession) -> MonitoringPerformanceService:
    return MonitoringPerformanceService(
        MonitoringMetricSeriesRepository(db_session), MonitoringMetricRepository(db_session)
    )


class TestMonitoringPerformanceService:
    async def test_summarizes_only_performance_relevant_metrics(
        self, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        latency_metric = await make_metric(
            db_session, organization_id=target.organization_id, metric_type=MetricType.LATENCY
        )
        cpu_metric = await make_metric(
            db_session, organization_id=target.organization_id, metric_type=MetricType.CPU_USAGE
        )
        series = MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session))
        for value in (10.0, 20.0, 30.0):
            await series.record(
                organization_id=target.organization_id,
                metric_id=latency_metric.id,
                target_id=target.id,
                value=value,
            )
        await series.record(
            organization_id=target.organization_id,
            metric_id=cpu_metric.id,
            target_id=target.id,
            value=99.0,
        )
        service = _service(db_session)
        summaries = await service.summarize_for_target(target.id)
        assert len(summaries) == 1
        assert summaries[0]["metric_type"] == MetricType.LATENCY
        assert summaries[0]["average"] == 20.0
        assert summaries[0]["sample_count"] == 3

    async def test_no_data_returns_empty(self, db_session: AsyncSession) -> None:
        target = await make_target(db_session)
        service = _service(db_session)
        summaries = await service.summarize_for_target(target.id)
        assert summaries == []
