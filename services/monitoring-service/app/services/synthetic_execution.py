"""Synthetic test execution orchestrator ("SYNTHETIC MONITORING"). Runs
a single :class:`~app.models.monitoring_synthetic_test
.MonitoringSyntheticTest` via :func:`app.collectors.synthetic
.run_synthetic_test` and persists its own outcome into
:class:`~app.models.monitoring_health.MonitoringHealth` (pass/fail) and,
where the collected data carries a numeric ``latency_ms``, into
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries` --
reusing the same tables every other collector already writes into
rather than a dedicated results table (see
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`'s
own docstring for why).

``MonitoringMetricSeries.metric_id`` and ``MonitoringHealth.target_id``
are both real, non-nullable foreign keys. A synthetic test has no
:class:`~app.models.monitoring_metric.MonitoringMetric` row of its own,
so :meth:`app.services.metric.MonitoringMetricService
.get_or_create_by_name` lazily resolves (and reuses across every
subsequent run) one shared ``"synthetic_latency_ms"`` metric per
organization. A *target-less* synthetic test (probing a bare external
endpoint, per :class:`~app.models.monitoring_synthetic_test
.MonitoringSyntheticTest`'s own docstring) similarly has no
:class:`~app.models.monitoring_target.MonitoringTarget` row to persist
against, so :meth:`app.services.target.MonitoringTargetService
.get_or_create` registers (and reuses) one lightweight
``CUSTOM_TARGET`` row representing the test itself. Two real
integrity-constraint failures this service's own test suite caught:
passing ``test.id`` directly as ``metric_id``, and passing it as
``target_id`` for a target-less test -- neither is ever a real row in
the table its own foreign key points at.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.events.base import DomainEvent

from app.collectors.context import CollectorContext
from app.collectors.synthetic import run_synthetic_test
from app.events.monitoring_events import SyntheticTestFailedEvent
from app.models.enums import HealthCheckType, MetricType, MonitoringTargetType
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.models.monitoring_target import MonitoringTarget
from app.services.health import MonitoringHealthService
from app.services.metric import MonitoringMetricService
from app.services.metric_series import MonitoringMetricSeriesService
from app.services.target import MonitoringTargetService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_SUCCESS_KEYS = ("reachable", "resolved", "valid")


class MonitoringSyntheticExecutionService:
    """Runs one synthetic test and persists its own outcome."""

    def __init__(
        self,
        health: MonitoringHealthService,
        metric_series: MonitoringMetricSeriesService,
        metrics: MonitoringMetricService,
        targets: MonitoringTargetService,
        context: CollectorContext,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._health = health
        self._metric_series = metric_series
        self._metrics = metrics
        self._targets = targets
        self._context = context
        self._publish_event = publish_event

    async def run(
        self, test: MonitoringSyntheticTest, target: MonitoringTarget | None
    ) -> HealthStatus:
        """Run *test* and persist its own outcome, returning the resolved status."""
        organization_id = test.organization_id
        target_id = await self._resolve_target_id(test, target)
        try:
            data = await run_synthetic_test(test, target, self._context)
        except Exception as exc:
            return await self._record_failure(organization_id, target_id, test, str(exc))

        succeeded = all(data.get(key, True) for key in _SUCCESS_KEYS if key in data)
        if "status_matches" in data:
            succeeded = succeeded and bool(data.get("status_matches"))
        if not succeeded:
            return await self._record_failure(organization_id, target_id, test, str(data))

        latency_ms = data.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            metric = await self._metrics.get_or_create_by_name(
                organization_id=organization_id,
                name="synthetic_latency_ms",
                metric_type=MetricType.LATENCY,
                unit="ms",
            )
            await self._metric_series.record(
                organization_id=organization_id,
                metric_id=metric.id,
                target_id=target_id,
                value=float(latency_ms),
                tags={"synthetic_test_id": str(test.id)},
            )
        await self._health.record(
            organization_id=organization_id,
            target_id=target_id,
            check_type=HealthCheckType.SERVICE_AVAILABILITY,
            status=HealthStatus.HEALTHY,
            message=f"Synthetic test {test.name!r} succeeded.",
        )
        return HealthStatus.HEALTHY

    async def _resolve_target_id(
        self, test: MonitoringSyntheticTest, target: MonitoringTarget | None
    ) -> UUID:
        """Return a real, persistable target id for *test*'s own outcome.

        Reuses *target*'s own id when the test is registered against a
        real target; otherwise registers (and reuses, on every later
        run) one lightweight ``CUSTOM_TARGET`` row representing the
        bare endpoint this test itself probes.
        """
        if target is not None:
            return target.id
        virtual_target = await self._targets.get_or_create(
            organization_id=test.organization_id,
            project_id=None,
            target_type=MonitoringTargetType.CUSTOM_TARGET,
            external_id=f"synthetic-test:{test.id}",
            name=test.name,
            target_metadata={},
        )
        return virtual_target.id

    async def _record_failure(
        self, organization_id: UUID, target_id: UUID, test: MonitoringSyntheticTest, reason: str
    ) -> HealthStatus:
        await self._health.record(
            organization_id=organization_id,
            target_id=target_id,
            check_type=HealthCheckType.SERVICE_AVAILABILITY,
            status=HealthStatus.UNHEALTHY,
            message=reason,
        )
        await self._publish_event(
            SyntheticTestFailedEvent(
                source_service="monitoring-service",
                payload={"synthetic_test_id": str(test.id), "reason": reason},
            )
        )
        return HealthStatus.UNHEALTHY


__all__ = ["EventPublisher", "MonitoringSyntheticExecutionService"]
