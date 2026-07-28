"""Tests for :class:`app.services.synthetic_execution
.MonitoringSyntheticExecutionService`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.enums.health_status import HealthStatus
from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.context import CollectorContext
from app.models.enums import SyntheticCheckType
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.services.synthetic_execution import MonitoringSyntheticExecutionService
from tests.conftest import (
    build_collector_context,
    build_synthetic_execution_service,
    make_synthetic_test,
    make_target,
)


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield build_collector_context(client)


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _service(
    db_session: AsyncSession, context: CollectorContext, publisher: _EventRecorder
) -> MonitoringSyntheticExecutionService:
    return build_synthetic_execution_service(db_session, context=context, publish_event=publisher)


class TestMonitoringSyntheticExecutionService:
    async def test_successful_http_check_records_healthy_and_latency(
        self, db_session: AsyncSession, context: CollectorContext, httpx_mock: HTTPXMock
    ) -> None:
        target = await make_target(db_session)
        test = await make_synthetic_test(
            db_session,
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=SyntheticCheckType.HTTP,
            parameters={"url": "http://example.internal/ping"},
        )
        httpx_mock.add_response(url="http://example.internal/ping", json={"ok": True})

        recorder = _EventRecorder()
        service = _service(db_session, context, recorder)
        status = await service.run(test, target)
        assert status == HealthStatus.HEALTHY

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert results[0].status == HealthStatus.HEALTHY

        series_repo = MonitoringMetricSeriesRepository(db_session)
        points = await series_repo.list_for_target(target.id)
        assert len(points) == 1

    async def test_status_mismatch_records_failure_and_publishes_event(
        self, db_session: AsyncSession, context: CollectorContext, httpx_mock: HTTPXMock
    ) -> None:
        target = await make_target(db_session)
        test = await make_synthetic_test(
            db_session,
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=SyntheticCheckType.HTTP,
            parameters={"url": "http://example.internal/ping", "expected_status": 200},
        )
        httpx_mock.add_response(url="http://example.internal/ping", status_code=503)

        recorder = _EventRecorder()
        service = _service(db_session, context, recorder)
        status = await service.run(test, target)
        assert status == HealthStatus.UNHEALTHY
        assert any(type(e).__name__ == "SyntheticTestFailedEvent" for e in recorder.events)

    async def test_unreachable_target_records_failure(
        self, db_session: AsyncSession, context: CollectorContext, httpx_mock: HTTPXMock
    ) -> None:
        target = await make_target(db_session)
        test = await make_synthetic_test(
            db_session,
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=SyntheticCheckType.HTTP,
            parameters={"url": "http://example.internal/ping"},
        )
        httpx_mock.add_exception(httpx.ConnectError("refused"))

        recorder = _EventRecorder()
        service = _service(db_session, context, recorder)
        status = await service.run(test, target)
        assert status == HealthStatus.UNHEALTHY

    async def test_run_raises_internally_is_treated_as_failure(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session)
        test = await make_synthetic_test(
            db_session,
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=SyntheticCheckType.HTTP,
            parameters={},  # missing 'url' -> ValidationError inside run_synthetic_test
        )

        recorder = _EventRecorder()
        service = _service(db_session, context, recorder)
        status = await service.run(test, target)
        assert status == HealthStatus.UNHEALTHY
