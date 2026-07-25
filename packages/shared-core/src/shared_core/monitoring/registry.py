"""Monitoring registry.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "MONITORING
REGISTRY": maintain registry for Services, Dependencies, Health Checks,
Metrics, Thresholds, Dashboards, Alert Rules. Composes the framework's
other registries (:class:`~shared_core.monitoring.health.HealthChecker`,
:class:`~shared_core.monitoring.dependencies.DependencyMonitor`,
:class:`~shared_core.monitoring.services.ServiceRegistry`, ...) into one
place rather than reimplementing registration a second time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared_core.monitoring.alerts import AlertDispatcher
from shared_core.monitoring.dependencies import DependencyMonitor
from shared_core.monitoring.health import DeepHealthChecker, HealthChecker
from shared_core.monitoring.services import ServiceRegistry
from shared_core.monitoring.thresholds import Threshold


@dataclass(slots=True)
class MonitoringRegistry:
    """The single registration point a service's monitoring setup goes through."""

    health: HealthChecker = field(default_factory=HealthChecker)
    deep_health: DeepHealthChecker = field(default_factory=DeepHealthChecker)
    dependencies: DependencyMonitor = field(default_factory=DependencyMonitor)
    services: ServiceRegistry = field(default_factory=ServiceRegistry)
    alerts: AlertDispatcher = field(default_factory=AlertDispatcher)
    _thresholds: dict[str, Threshold] = field(default_factory=dict)
    _dashboards: dict[str, str] = field(default_factory=dict)

    def register_threshold(self, threshold: Threshold) -> None:
        """Register a metric's configured threshold."""
        self._thresholds[threshold.metric_name] = threshold

    def get_threshold(self, metric_name: str) -> Threshold | None:
        """Return the registered threshold for *metric_name*, if any."""
        return self._thresholds.get(metric_name)

    def thresholds(self) -> dict[str, Threshold]:
        """Return every registered threshold, by metric name."""
        return dict(self._thresholds)

    def register_dashboard(self, name: str, description: str) -> None:
        """Register a known dashboard (a Grafana dashboard UID, an OpenSearch saved object, ...)."""
        self._dashboards[name] = description

    def dashboards(self) -> dict[str, str]:
        """Return every registered dashboard, name to description."""
        return dict(self._dashboards)


__all__ = ["MonitoringRegistry"]
