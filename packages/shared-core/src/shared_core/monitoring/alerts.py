"""Alert integration.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "ALERT INTEGRATION":
Health Failure, Dependency Failure, High CPU, High Memory, Disk Full,
Database Down, Redis Down, Queue Overflow, Storage Failure, Plugin
Failure, Connector Failure, Worker Failure, High Error Rate, High
Latency.

Defines the alert data model and trigger/fan-out logic; actually
*delivering* an alert (email/Slack/PagerDuty/...) is a future
Notification Framework's concern -- this module's ``AlertSink`` is what
such an integration implements and registers, and every triggered alert
is audit-logged via :mod:`shared_core.logging` regardless of whether any
sink is registered, so nothing is silently lost even before one exists.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from shared_core.logging.logger import get_logger
from shared_core.monitoring.thresholds import ThresholdLevel

logger = get_logger("shared_core.monitoring.alerts")


class AlertCategory(StrEnum):
    """The kind of condition an alert represents, per docs/023 "ALERT INTEGRATION"."""

    HEALTH_FAILURE = "health_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    DISK_FULL = "disk_full"
    DATABASE_DOWN = "database_down"
    REDIS_DOWN = "redis_down"
    QUEUE_OVERFLOW = "queue_overflow"
    STORAGE_FAILURE = "storage_failure"
    PLUGIN_FAILURE = "plugin_failure"
    CONNECTOR_FAILURE = "connector_failure"
    WORKER_FAILURE = "worker_failure"
    HIGH_ERROR_RATE = "high_error_rate"
    HIGH_LATENCY = "high_latency"


@dataclass(frozen=True, slots=True)
class Alert:
    """One triggered alert."""

    category: AlertCategory
    level: ThresholdLevel
    message: str
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metric_name: str | None = None
    value: float | None = None


AlertSink = Callable[[Alert], Awaitable[None]]


@dataclass(slots=True)
class AlertDispatcher:
    """Fans a triggered alert out to every registered sink, and always audits it."""

    _sinks: list[AlertSink] = field(default_factory=list)

    def register_sink(self, sink: AlertSink) -> None:
        """Register a callable that delivers an alert somewhere (email/Slack/PagerDuty/...)."""
        self._sinks.append(sink)

    async def trigger(self, alert: Alert) -> None:
        """Audit-log *alert*, then dispatch it to every registered sink."""
        logger.audit(
            "monitoring.alert",
            resource=alert.category.value,
            outcome=alert.level.value,
            message=alert.message,
            metric_name=alert.metric_name,
            value=alert.value,
        )
        for sink in self._sinks:
            await sink(alert)


__all__ = ["Alert", "AlertCategory", "AlertDispatcher", "AlertSink"]
