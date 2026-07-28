"""Maps a :class:`~app.models.monitoring_collector.MonitoringCollector`'s
own ``collector_key`` onto the actual collector function that gathers
its data. Matches ``services/validation-service``'s own
:mod:`app.collectors.registry`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.collectors.network import (
    collect_certificate,
    collect_connectivity,
    collect_dns,
    collect_http,
    collect_port,
)
from app.collectors.remote import collect_via_automation_job
from app.collectors.service_state import (
    collect_configuration_compliance,
    collect_configuration_drift,
    collect_discovery_job,
    collect_inventory_asset,
    collect_validation_posture,
    collect_workflow_instance,
)
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget

Collector = Callable[
    [MonitoringCollector, MonitoringTarget, CollectorContext], Awaitable[dict[str, Any]]
]

_DEFAULT_COLLECTORS: dict[str, Collector] = {
    "connectivity": collect_connectivity,
    "port": collect_port,
    "dns": collect_dns,
    "certificate": collect_certificate,
    "http": collect_http,
    "automation_job": collect_via_automation_job,
    "inventory_asset": collect_inventory_asset,
    "configuration_drift": collect_configuration_drift,
    "configuration_compliance": collect_configuration_compliance,
    "workflow_instance": collect_workflow_instance,
    "discovery_job": collect_discovery_job,
    "validation_posture": collect_validation_posture,
}


class CollectorRegistry:
    """Looks up and invokes the collector named by a collector's own ``collector_key``."""

    def __init__(self, collectors: dict[str, Collector] | None = None) -> None:
        self._collectors = dict(collectors) if collectors is not None else dict(_DEFAULT_COLLECTORS)

    def register(self, collector_key: str, collector: Collector) -> None:
        """Register a custom collector under *collector_key* ("Custom Metrics")."""
        self._collectors[collector_key] = collector

    async def collect(
        self, collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
    ) -> dict[str, Any]:
        """Run the collector named by *collector*'s own ``collector_key``.

        Raises:
            ValidationError: If no collector is registered under that key.
        """
        fn = self._collectors.get(collector.collector_key)
        if fn is None:
            raise ValidationError(
                f"Collector {collector.id!r} names unknown collector_key "
                f"{collector.collector_key!r}."
            )
        return await fn(collector, target, context)


__all__ = ["Collector", "CollectorRegistry"]
