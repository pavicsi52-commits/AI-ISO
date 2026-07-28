"""Central collection orchestrator ("Monitoring Engine", "Distributed
Collectors", "Async Processing") -- runs a
:class:`~app.models.monitoring_collector.MonitoringCollector` against
one or many :class:`~app.models.monitoring_target.MonitoringTarget`
rows, persists the result, evaluates thresholds/rules, updates
health/availability, and publishes events.

Mirrors ``services/validation-service``'s own
``ValidationExecutionService`` split between I/O collection (safe to
run concurrently via ``asyncio.gather``) and database persistence
(always sequential) -- a real production bug that service hit once
already: ``AsyncSession`` is not safe for concurrent use by multiple
asyncio tasks within one event loop, even for reads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.events.base import DomainEvent
from shared_core.monitoring.thresholds import ThresholdLevel

from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.events.monitoring_events import (
    HealthChangedEvent,
    MetricCollectedEvent,
    ThresholdExceededEvent,
    ThresholdRecoveredEvent,
)
from app.models.enums import AvailabilityStatus, HealthCheckType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_rule import MonitoringRuleRepository
from app.repositories.monitoring_threshold import MonitoringThresholdRepository
from app.rules.evaluator import evaluate_rule
from app.rules.thresholds import evaluate_threshold
from app.services.availability import MonitoringAvailabilityService
from app.services.health import MonitoringHealthService
from app.services.metric_series import MonitoringMetricSeriesService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_HEALTH_SIGNAL_COLLECTOR_KEYS = frozenset(
    {
        "dns",
        "inventory_asset",
        "configuration_drift",
        "configuration_compliance",
        "workflow_instance",
        "discovery_job",
        "validation_posture",
    }
)
_METRIC_VALUE_KEYS: dict[str, str] = {
    "connectivity": "latency_ms",
    "port": "latency_ms",
    "certificate": "days_remaining",
    "http": "latency_ms",
}
_THRESHOLD_LEVEL_TO_STATUS: dict[ThresholdLevel, HealthStatus] = {
    ThresholdLevel.CRITICAL: HealthStatus.UNHEALTHY,
    ThresholdLevel.HIGH: HealthStatus.WARNING,
    ThresholdLevel.MEDIUM: HealthStatus.WARNING,
    ThresholdLevel.LOW: HealthStatus.DEGRADED,
    ThresholdLevel.INFORMATIONAL: HealthStatus.DEGRADED,
}


@dataclass(frozen=True, slots=True)
class _Collected:
    collector: MonitoringCollector
    target: MonitoringTarget
    data: dict[str, Any] | None
    error: str | None


class MonitoringCollectionService:
    """Runs distributed collectors against targets and persists their results."""

    def __init__(
        self,
        metrics: MonitoringMetricRepository,
        thresholds: MonitoringThresholdRepository,
        rules: MonitoringRuleRepository,
        metric_series: MonitoringMetricSeriesService,
        health: MonitoringHealthService,
        availability: MonitoringAvailabilityService,
        registry: CollectorRegistry,
        context: CollectorContext,
        *,
        publish_event: EventPublisher,
        max_parallel_collections: int = 10,
    ) -> None:
        self._metrics = metrics
        self._thresholds = thresholds
        self._rules = rules
        self._metric_series = metric_series
        self._health = health
        self._availability = availability
        self._registry = registry
        self._context = context
        self._publish_event = publish_event
        self._max_parallel_collections = max_parallel_collections

    async def _collect_one(
        self, collector: MonitoringCollector, target: MonitoringTarget
    ) -> _Collected:
        try:
            data = await self._registry.collect(collector, target, self._context)
            return _Collected(collector, target, data, None)
        except Exception as exc:
            return _Collected(collector, target, None, str(exc))

    async def run_collector(
        self, collector: MonitoringCollector, targets: list[MonitoringTarget]
    ) -> None:
        """Run *collector* against every target in *targets*, persisting
        results sequentially after concurrently gathering their own
        collection I/O ("Async Processing").
        """
        semaphore = asyncio.Semaphore(self._max_parallel_collections)

        async def _bounded(target: MonitoringTarget) -> _Collected:
            async with semaphore:
                return await self._collect_one(collector, target)

        collected_batch = await asyncio.gather(*(_bounded(target) for target in targets))
        for collected in collected_batch:
            await self._persist_one(collected)

    async def _persist_one(self, collected: _Collected) -> None:
        if collected.error is not None or collected.data is None:
            await self._record_health(
                collected.target,
                status=HealthStatus.UNHEALTHY,
                message=collected.error or "Collector returned no data.",
            )
            return

        collector_key = collected.collector.collector_key
        if collector_key in _HEALTH_SIGNAL_COLLECTOR_KEYS:
            await self._persist_health_signal(collected)
        elif collector_key == "automation_job":
            await self._persist_named_metrics(collected)
        else:
            await self._persist_single_metric(collected)

    async def _persist_health_signal(self, collected: _Collected) -> None:
        data = collected.data or {}
        has_breach_counts = any(
            data.get(key)
            for key in ("unresolved_drift_count", "non_compliant_count", "failed_count")
        )
        explicit_failure = any(
            key in data and not data[key] for key in ("resolved", "reachable", "valid")
        )
        healthy = not has_breach_counts and not explicit_failure
        status = HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED
        await self._record_health(collected.target, status=status, message=str(data))

    async def _persist_named_metrics(self, collected: _Collected) -> None:
        data = collected.data or {}
        metrics = await self._metrics.list_for_collector(collected.collector.id)
        for metric in metrics:
            value = data.get(metric.name)
            if isinstance(value, (int, float)):
                await self._record_metric(collected.target, metric_id=metric.id, value=float(value))

    async def _persist_single_metric(self, collected: _Collected) -> None:
        data = collected.data or {}
        collector_key = collected.collector.collector_key
        value_key = _METRIC_VALUE_KEYS.get(collector_key)

        if collector_key in ("connectivity", "port"):
            status = AvailabilityStatus.UP if data.get("reachable") else AvailabilityStatus.DOWN
            await self._availability.record_status(
                organization_id=collected.target.organization_id,
                target_id=collected.target.id,
                status=status,
            )

        metrics = await self._metrics.list_for_collector(collected.collector.id)
        if not metrics or value_key is None:
            return
        raw_value = data.get(value_key)
        if not isinstance(raw_value, (int, float)):
            return
        for metric in metrics:
            await self._record_metric(collected.target, metric_id=metric.id, value=float(raw_value))

    async def _record_metric(
        self, target: MonitoringTarget, *, metric_id: UUID, value: float
    ) -> None:
        await self._metric_series.record(
            organization_id=target.organization_id,
            metric_id=metric_id,
            target_id=target.id,
            value=value,
        )
        await self._publish_event(
            MetricCollectedEvent(
                source_service="monitoring-service",
                payload={"target_id": str(target.id), "metric_id": str(metric_id), "value": value},
            )
        )
        await self._evaluate_thresholds_and_rules(target, metric_id=metric_id, value=value)

    async def _evaluate_thresholds_and_rules(
        self, target: MonitoringTarget, *, metric_id: UUID, value: float
    ) -> None:
        breached_level: ThresholdLevel | None = None
        for threshold in await self._thresholds.list_for_metric(metric_id):
            level = evaluate_threshold(threshold, value, metric_name=str(metric_id))
            if level is not None:
                breached_level = level
                break
        for rule in await self._rules.list_for_metric(metric_id):
            if evaluate_rule(rule, {"value": value}):
                breached_level = rule.severity
                break

        if breached_level is not None:
            await self._publish_event(
                ThresholdExceededEvent(
                    source_service="monitoring-service",
                    payload={
                        "target_id": str(target.id),
                        "metric_id": str(metric_id),
                        "value": value,
                        "level": str(breached_level),
                    },
                )
            )
            await self._record_health(
                target,
                status=_THRESHOLD_LEVEL_TO_STATUS[breached_level],
                message=f"Metric {metric_id!r} breached threshold level {breached_level!r}.",
            )
        else:
            await self._publish_event(
                ThresholdRecoveredEvent(
                    source_service="monitoring-service",
                    payload={"target_id": str(target.id), "metric_id": str(metric_id)},
                )
            )

    async def _record_health(
        self, target: MonitoringTarget, *, status: HealthStatus, message: str
    ) -> None:
        await self._health.record(
            organization_id=target.organization_id,
            target_id=target.id,
            check_type=HealthCheckType.COMPONENT_HEALTH,
            status=status,
            message=message,
        )
        await self._publish_event(
            HealthChangedEvent(
                source_service="monitoring-service",
                payload={"target_id": str(target.id), "status": str(status)},
            )
        )


__all__ = ["EventPublisher", "MonitoringCollectionService"]
