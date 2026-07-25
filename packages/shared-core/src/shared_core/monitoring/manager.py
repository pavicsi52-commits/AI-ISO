"""Monitoring manager.

The primary developer-facing entry point a service actually calls,
mirroring :class:`shared_core.events.manager.EventManager`'s role: wires
the registry, collector, heartbeat, availability, and alerting together
behind a small, cohesive API.
"""

from __future__ import annotations

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.alerts import Alert, AlertCategory
from shared_core.monitoring.application import ApplicationStatistics
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.collector import MonitoringCollector
from shared_core.monitoring.heartbeat import Heartbeat, build_heartbeat
from shared_core.monitoring.registry import MonitoringRegistry
from shared_core.monitoring.sla import ServiceLevelObjective, SlaReport, build_sla_report
from shared_core.monitoring.status import calculate_status
from shared_core.monitoring.thresholds import ThresholdLevel


class MonitoringManager:
    """The primary developer-facing entry point for the Enterprise Monitoring Framework."""

    def __init__(
        self,
        *,
        service_name: str,
        version: str,
        environment: str,
        registry: MonitoringRegistry | None = None,
        collector: MonitoringCollector | None = None,
        statistics: ApplicationStatistics | None = None,
        availability: AvailabilityTracker | None = None,
        sla_objective: ServiceLevelObjective | None = None,
    ) -> None:
        self.service_name = service_name
        self.version = version
        self.environment = environment
        self.registry = registry or MonitoringRegistry()
        self.statistics = statistics or ApplicationStatistics()
        self.availability = availability or AvailabilityTracker()
        self.collector = collector or MonitoringCollector(
            self.registry.dependencies, self.availability
        )
        self.sla_objective = sla_objective or ServiceLevelObjective()
        self._maintenance_mode = False

    def enter_maintenance(self) -> None:
        """Force overall status to ``MAINTENANCE`` regardless of what checks report."""
        self._maintenance_mode = True

    def exit_maintenance(self) -> None:
        """Return to automatically-calculated overall status."""
        self._maintenance_mode = False

    async def overall_status(self) -> HealthStatus:
        """Calculate the current overall status ("Status shall be calculated automatically")."""
        readiness = await self.registry.health.run_all()
        dependency_status = await self.registry.dependencies.overall_status()
        services_status = self.registry.services.overall_status()
        return calculate_status(
            [readiness.status, dependency_status, services_status],
            maintenance_mode=self._maintenance_mode,
        )

    async def heartbeat(self) -> Heartbeat:
        """Build this process's current heartbeat ("Every service shall publish heartbeat")."""
        status = await self.overall_status()
        return build_heartbeat(
            service_name=self.service_name,
            version=self.version,
            environment=self.environment,
            status=status,
            statistics=self.statistics,
        )

    async def sla_report(self) -> SlaReport:
        """Build the current SLA report against this manager's configured objective."""
        return build_sla_report(
            objective=self.sla_objective,
            statistics=self.statistics,
            availability=self.availability,
        )

    async def trigger_alert(
        self,
        category: AlertCategory,
        level: ThresholdLevel,
        message: str,
        *,
        metric_name: str | None = None,
        value: float | None = None,
    ) -> None:
        """Trigger an alert through the registry's dispatcher."""
        await self.registry.alerts.trigger(
            Alert(
                category=category,
                level=level,
                message=message,
                metric_name=metric_name,
                value=value,
            )
        )

    async def start(self) -> None:
        """Start background collection."""
        await self.collector.start()

    async def stop(self) -> None:
        """Stop background collection."""
        await self.collector.stop()


__all__ = ["MonitoringManager"]
