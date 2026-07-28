"""Tests for :class:`app.services.metric_series.MonitoringMetricSeriesService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.services.metric_series import MonitoringMetricSeriesService
from tests.conftest import make_metric, make_target


def _service(db_session: AsyncSession) -> MonitoringMetricSeriesService:
    return MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session))


class TestMonitoringMetricSeriesService:
    async def test_record_defaults_recorded_at(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        metric = await make_metric(db_session)
        point = await service.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=42.0,
        )
        assert point.value == 42.0
        assert point.recorded_at is not None

    async def test_list_for_target_filters_by_metric_and_since(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        metric = await make_metric(db_session)
        old = datetime.now(UTC) - timedelta(days=2)
        recent = datetime.now(UTC)
        await service.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=1.0,
            recorded_at=old,
        )
        await service.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=2.0,
            recorded_at=recent,
        )
        all_points = await service.list_for_target(target.id, metric_id=metric.id)
        assert len(all_points) == 2
        recent_only = await service.list_for_target(
            target.id, metric_id=metric.id, since=datetime.now(UTC) - timedelta(hours=1)
        )
        assert len(recent_only) == 1
        assert recent_only[0].value == 2.0

    async def test_delete_older_than(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        metric = await make_metric(db_session)
        old = datetime.now(UTC) - timedelta(days=100)
        await service.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=1.0,
            recorded_at=old,
        )
        deleted = await service.delete_older_than(datetime.now(UTC) - timedelta(days=90))
        assert deleted == 1
