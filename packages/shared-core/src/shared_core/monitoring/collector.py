"""Monitoring collector.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "PERFORMANCE": Async
collection, Efficient polling, Minimal overhead, Configurable polling.
Periodically captures application/resource snapshots and runs
dependency checks on its own background task, so a request handler
never pays for a live check.
"""

from __future__ import annotations

import asyncio
import contextlib

from shared_core.enums.health_status import HealthStatus
from shared_core.logging.logger import get_logger
from shared_core.monitoring.application import ApplicationSnapshot, capture_application_snapshot
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.checks import DependencyCheckResult
from shared_core.monitoring.constants import DEFAULT_COLLECTION_INTERVAL_SECONDS
from shared_core.monitoring.dependencies import DependencyMonitor
from shared_core.monitoring.resources import ResourceSnapshot, capture_resource_snapshot
from shared_core.monitoring.status import calculate_status

logger = get_logger("shared_core.monitoring.collector")


class MonitoringCollector:
    """Runs periodic collection in the background and caches the latest results."""

    def __init__(
        self,
        dependency_monitor: DependencyMonitor,
        availability: AvailabilityTracker,
        *,
        interval_seconds: float = DEFAULT_COLLECTION_INTERVAL_SECONDS,
    ) -> None:
        self._dependency_monitor = dependency_monitor
        self._availability = availability
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.latest_application: ApplicationSnapshot | None = None
        self.latest_resources: ResourceSnapshot | None = None
        self.latest_dependencies: list[DependencyCheckResult] = []
        self.latest_status: HealthStatus = HealthStatus.UNKNOWN

    async def collect_once(self) -> HealthStatus:
        """Run one collection cycle immediately, updating the cached latest results."""
        self.latest_application = capture_application_snapshot()
        self.latest_resources = capture_resource_snapshot()
        self.latest_dependencies = await self._dependency_monitor.check_all()
        self.latest_status = calculate_status(dep.status for dep in self.latest_dependencies)
        self._availability.record(self.latest_status)
        return self.latest_status

    async def start(self) -> None:
        """Start the periodic background collection loop ("Configurable polling")."""
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self._running:
            try:
                await self.collect_once()
            except Exception:
                logger.warning("monitoring collection cycle failed")
            await asyncio.sleep(self._interval_seconds)

    async def stop(self) -> None:
        """Stop the periodic background collection loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


__all__ = ["MonitoringCollector"]
