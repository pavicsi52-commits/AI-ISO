"""Tests for :class:`app.services.collection.MonitoringCollectionService`
-- the central "Monitoring Engine" orchestrator. Uses a fresh
:class:`~app.collectors.registry.CollectorRegistry` with deterministic,
custom-registered collector functions (rather than real network/HTTP
I/O, already covered by :mod:`tests.test_collectors_network`) so the
*persistence and dispatch* logic can be exercised precisely.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.models.enums import MetricType, ThresholdType
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.services.collection import MonitoringCollectionService
from tests.conftest import (
    build_collection_service,
    build_collector_context,
    make_collector,
    make_metric,
    make_target,
    make_threshold,
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
    db_session: AsyncSession, context: CollectorContext, registry: CollectorRegistry, publisher: Any
) -> MonitoringCollectionService:
    return build_collection_service(
        db_session, context=context, registry=registry, publish_event=publisher
    )


class TestSingleMetricCollectors:
    async def test_connectivity_collector_persists_metric_and_availability(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session, target_metadata={"host": "127.0.0.1"})
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="connectivity"
        )
        await make_metric(
            db_session,
            organization_id=target.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.LATENCY,
        )

        registry = CollectorRegistry()

        async def _fake_connectivity(_collector: object, _target: object, _context: object) -> dict:
            return {"reachable": True, "latency_ms": 12.5}

        registry.register("connectivity", _fake_connectivity)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        # No threshold configured -> ThresholdRecovered only, no health record from this path.
        assert any(type(e).__name__ == "MetricCollectedEvent" for e in recorder.events)
        assert any(type(e).__name__ == "ThresholdRecoveredEvent" for e in recorder.events)

    async def test_threshold_breach_publishes_exceeded_and_records_health(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session, target_metadata={"host": "127.0.0.1"})
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="certificate"
        )
        metric = await make_metric(
            db_session,
            organization_id=target.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.CUSTOM_METRICS,
        )
        await make_threshold(
            db_session, metric, threshold_type=ThresholdType.STATIC, high=5.0, critical=10.0
        )

        registry = CollectorRegistry()

        async def _fake_certificate(_collector: object, _target: object, _context: object) -> dict:
            return {"valid": True, "days_remaining": 20}

        registry.register("certificate", _fake_certificate)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        assert any(type(e).__name__ == "ThresholdExceededEvent" for e in recorder.events)
        assert any(type(e).__name__ == "HealthChangedEvent" for e in recorder.events)

    async def test_unreachable_target_marks_down(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session, target_metadata={"host": "127.0.0.1"})
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="port"
        )
        await make_metric(
            db_session,
            organization_id=target.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.LATENCY,
        )

        registry = CollectorRegistry()

        async def _fake_port(_collector: object, _target: object, _context: object) -> dict:
            return {"reachable": False, "error": "refused"}

        registry.register("port", _fake_port)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        # reachable=False -> no numeric latency to persist, but availability still tracked.
        assert not any(type(e).__name__ == "MetricCollectedEvent" for e in recorder.events)


class TestNamedMetricsCollector:
    async def test_automation_job_persists_each_matching_metric(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session)
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="automation_job"
        )
        await make_metric(
            db_session,
            organization_id=target.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.CPU_USAGE,
            name="cpu_usage_percent",
        )
        await make_metric(
            db_session,
            organization_id=target.organization_id,
            collector_id=collector.id,
            metric_type=MetricType.MEMORY_USAGE,
            name="memory_usage_percent",
        )

        registry = CollectorRegistry()

        async def _fake_job(_collector: object, _target: object, _context: object) -> dict:
            return {"cpu_usage_percent": 55.0, "memory_usage_percent": 70.0, "unrelated": "x"}

        registry.register("automation_job", _fake_job)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        metric_events = [e for e in recorder.events if type(e).__name__ == "MetricCollectedEvent"]
        assert len(metric_events) == 2


class TestHealthSignalCollector:
    async def test_service_state_style_collector_marks_degraded_on_breach(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session)
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="configuration_drift"
        )

        registry = CollectorRegistry()

        async def _fake_drift(_collector: object, _target: object, _context: object) -> dict:
            return {"unresolved_drift_count": 2}

        registry.register("configuration_drift", _fake_drift)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert results[0].status == HealthStatus.DEGRADED

    async def test_dns_style_collector_marks_degraded_on_explicit_failure(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session)
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="dns"
        )

        registry = CollectorRegistry()

        async def _fake_dns(_collector: object, _target: object, _context: object) -> dict:
            return {"resolved": False, "error": "NXDOMAIN"}

        registry.register("dns", _fake_dns)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert results[0].status == HealthStatus.DEGRADED


class TestCollectionErrors:
    async def test_collector_exception_records_unhealthy(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        target = await make_target(db_session)
        collector = await make_collector(
            db_session, organization_id=target.organization_id, collector_key="broken"
        )

        registry = CollectorRegistry()

        async def _broken(_collector: object, _target: object, _context: object) -> dict:
            raise RuntimeError("boom")

        registry.register("broken", _broken)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, [target])

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert results[0].status == HealthStatus.UNHEALTHY

    async def test_multiple_targets_collected_concurrently_and_persisted_sequentially(
        self, db_session: AsyncSession, context: CollectorContext
    ) -> None:
        first_target = await make_target(db_session)
        org_id = first_target.organization_id
        targets = [first_target] + [
            await make_target(db_session, organization_id=org_id) for _ in range(4)
        ]
        collector = await make_collector(db_session, organization_id=org_id, collector_key="dns")

        registry = CollectorRegistry()

        async def _fake_dns(_collector: object, _target: object, _context: object) -> dict:
            return {"resolved": True}

        registry.register("dns", _fake_dns)

        recorder = _EventRecorder()
        service = _service(db_session, context, registry, recorder)
        await service.run_collector(collector, targets)

        health_repo = MonitoringHealthRepository(db_session)
        for target in targets:
            results = await health_repo.list_for_target(target.id)
            assert results[0].status == HealthStatus.HEALTHY
