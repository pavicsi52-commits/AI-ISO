"""Tests for the read-only ``/monitoring/health``, ``/monitoring/availability``,
and ``/monitoring/performance`` routers -- none has a create endpoint of
its own (populated by the collection engine, not a direct API write), so
each test seeds state directly via the matching service before asserting
on the API response.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AvailabilityStatus, HealthCheckType, MetricType
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService
from app.services.metric import MonitoringMetricService
from app.services.metric_series import MonitoringMetricSeriesService
from tests.conftest import AuthHeadersFn, make_target


class TestMonitoringHealthApi:
    async def test_list_health_for_target(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        await MonitoringHealthService(MonitoringHealthRepository(db_session)).record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.HEARTBEAT,
            status=HealthStatus.HEALTHY,
        )
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/health", params={"target_id": str(target.id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/monitoring/health", params={"target_id": str(uuid.uuid4())})
        assert response.status_code == 401


class TestMonitoringAvailabilityApi:
    async def test_list_availability_for_target(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        await MonitoringAvailabilityService(
            MonitoringAvailabilityRepository(db_session)
        ).record_status(
            organization_id=target.organization_id,
            target_id=target.id,
            status=AvailabilityStatus.UP,
        )
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/availability", params={"target_id": str(target.id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/monitoring/availability", params={"target_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401


class TestMonitoringPerformanceApi:
    async def test_returns_performance_summary(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        metric = await MonitoringMetricService(MonitoringMetricRepository(db_session)).create(
            organization_id=target.organization_id,
            collector_id=None,
            metric_type=MetricType.LATENCY,
            name="latency_ms",
            unit="ms",
        )
        series = MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session))
        await series.record(
            organization_id=target.organization_id,
            metric_id=metric.id,
            target_id=target.id,
            value=15.0,
        )
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/performance", params={"target_id": str(target.id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["metrics"][0]["metric_type"] == "latency"

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/monitoring/performance", params={"target_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
