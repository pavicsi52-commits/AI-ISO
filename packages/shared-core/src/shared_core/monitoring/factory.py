"""Enterprise Monitoring Framework factory.

Assembles a :class:`~shared_core.monitoring.manager.MonitoringManager`
(registry, collector, statistics, availability, SLA objective) into the
one object a service builds exactly once at startup, mirroring
:func:`shared_core.events.factory.create_event_framework` (Prompt 020).
"""

from __future__ import annotations

from shared_core.monitoring.manager import MonitoringManager
from shared_core.monitoring.sla import ServiceLevelObjective


async def create_monitoring_framework(
    *,
    service_name: str,
    version: str,
    environment: str,
    sla_objective: ServiceLevelObjective | None = None,
    start_collection: bool = True,
) -> MonitoringManager:
    """Build a :class:`MonitoringManager` and, by default, start its background collection loop."""
    manager = MonitoringManager(
        service_name=service_name,
        version=version,
        environment=environment,
        sla_objective=sla_objective,
    )
    if start_collection:
        await manager.start()
    return manager


__all__ = ["create_monitoring_framework"]
