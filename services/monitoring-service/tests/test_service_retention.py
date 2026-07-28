"""Tests for :class:`app.services.retention.MonitoringRetentionService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AggregationFunction, MetricType
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.repositories.monitoring_retention import MonitoringRetentionRepository
from app.services.metric_series import MonitoringMetricSeriesService
from app.services.retention import MonitoringRetentionService
from tests.conftest import make_metric, make_target


def _service(db_session: AsyncSession) -> MonitoringRetentionService:
    return MonitoringRetentionService(
        MonitoringRetentionRepository(db_session),
        MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session)),
    )


class TestMonitoringRetentionService:
    async def test_create_and_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            metric_type=MetricType.CPU_USAGE,
            retention_days=30,
            downsampling_function=AggregationFunction.AVG,
            downsampling_interval_seconds=300.0,
            is_active=True,
        )
        policies = await service.list_for_org(org_id)
        assert len(policies) == 1
        assert policies[0].retention_days == 30

    async def test_enforce_for_org_deletes_old_points(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        target = await make_target(db_session)
        metric = await make_metric(db_session, organization_id=target.organization_id)
        await service.create(
            organization_id=target.organization_id,
            metric_type=MetricType.CPU_USAGE,
            retention_days=1,
            downsampling_function=None,
            downsampling_interval_seconds=None,
            is_active=True,
        )
        series_service = MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session))
        old = datetime.now(UTC) - timedelta(days=5)
        await series_service.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=1.0,
            recorded_at=old,
        )
        deleted = await service.enforce_for_org(target.organization_id, MetricType.CPU_USAGE)
        assert deleted == 1

    async def test_enforce_for_org_falls_back_to_platform_default(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        deleted = await service.enforce_for_org(org_id, MetricType.MEMORY_USAGE)
        assert deleted == 0
