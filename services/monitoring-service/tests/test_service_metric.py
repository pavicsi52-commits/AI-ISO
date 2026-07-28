"""Tests for :class:`app.services.metric.MonitoringMetricService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MetricType
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.services.metric import MonitoringMetricService
from tests.conftest import make_collector


def _service(db_session: AsyncSession) -> MonitoringMetricService:
    return MonitoringMetricService(MonitoringMetricRepository(db_session))


class TestMonitoringMetricService:
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        metric = await service.create(
            organization_id=uuid.uuid4(),
            collector_id=None,
            metric_type=MetricType.CPU_USAGE,
            name="cpu_usage_percent",
            unit="percent",
        )
        fetched = await service.get_by_id(metric.id)
        assert fetched.name == "cpu_usage_percent"

    async def test_get_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            collector_id=None,
            metric_type=MetricType.MEMORY_USAGE,
            name="memory_usage_percent",
            unit=None,
        )
        metrics = await service.list_for_org(org_id)
        assert len(metrics) == 1

    async def test_list_for_collector(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        collector = await make_collector(db_session)
        await service.create(
            organization_id=collector.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.LATENCY,
            name="latency_ms",
            unit="ms",
        )
        metrics = await service.list_for_collector(collector.id)
        assert len(metrics) == 1

    async def test_get_or_create_by_name_creates_new(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        metric = await service.get_or_create_by_name(
            organization_id=org_id, name="synthetic_latency_ms", metric_type=MetricType.LATENCY
        )
        assert metric.name == "synthetic_latency_ms"

    async def test_get_or_create_by_name_reuses_existing(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        first = await service.get_or_create_by_name(
            organization_id=org_id, name="synthetic_latency_ms", metric_type=MetricType.LATENCY
        )
        second = await service.get_or_create_by_name(
            organization_id=org_id, name="synthetic_latency_ms", metric_type=MetricType.LATENCY
        )
        assert second.id == first.id
