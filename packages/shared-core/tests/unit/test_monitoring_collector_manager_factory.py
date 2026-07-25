"""Tests for collector.py, manager.py, and factory.py."""

from __future__ import annotations

import asyncio

import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring import collector as collector_module
from shared_core.monitoring.alerts import AlertCategory
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.checks import DependencyCheckResult
from shared_core.monitoring.collector import MonitoringCollector
from shared_core.monitoring.dependencies import DependencyMonitor
from shared_core.monitoring.factory import create_monitoring_framework
from shared_core.monitoring.manager import MonitoringManager
from shared_core.monitoring.thresholds import ThresholdLevel

# --- collector.py ---


async def test_collector_collect_once_captures_a_snapshot_and_updates_status() -> None:
    monitor = DependencyMonitor()
    monitor.register("always_healthy", _healthy_check)
    availability = AvailabilityTracker()
    collector = MonitoringCollector(monitor, availability)

    status = await collector.collect_once()

    assert status == HealthStatus.HEALTHY
    assert collector.latest_application is not None
    assert collector.latest_resources is not None
    assert collector.latest_dependencies[0].name == "dep"


async def test_collector_collect_once_reports_the_worst_dependency_status() -> None:
    monitor = DependencyMonitor()
    monitor.register("bad", _unhealthy_check)
    collector = MonitoringCollector(monitor, AvailabilityTracker())

    status = await collector.collect_once()

    assert status == HealthStatus.UNHEALTHY


async def test_collector_start_and_stop_runs_the_background_loop() -> None:
    monitor = DependencyMonitor()
    monitor.register("always_healthy", _healthy_check)
    collector = MonitoringCollector(monitor, AvailabilityTracker(), interval_seconds=0.01)

    await collector.start()
    await asyncio.sleep(0.05)
    await collector.stop()

    assert collector.latest_status == HealthStatus.HEALTHY


async def test_collector_loop_logs_and_survives_a_collect_once_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> None:
        raise RuntimeError("snapshot capture blew up")

    monkeypatch.setattr(collector_module, "capture_application_snapshot", _raise)
    collector = MonitoringCollector(
        DependencyMonitor(), AvailabilityTracker(), interval_seconds=0.01
    )

    await collector.start()
    await asyncio.sleep(0.05)
    await collector.stop()

    assert collector.latest_application is None


async def test_collector_stop_is_safe_to_call_when_never_started() -> None:
    collector = MonitoringCollector(DependencyMonitor(), AvailabilityTracker())

    await collector.stop()


async def test_collector_survives_a_raising_dependency_check_across_loop_iterations() -> None:
    monitor = DependencyMonitor()
    monitor.register("flaky", _raising_check)
    collector = MonitoringCollector(monitor, AvailabilityTracker(), interval_seconds=0.01)

    await collector.start()
    await asyncio.sleep(0.05)
    await collector.stop()

    assert collector.latest_status == HealthStatus.UNHEALTHY


# --- manager.py ---


async def test_manager_overall_status_is_healthy_with_nothing_registered() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")

    assert await manager.overall_status() == HealthStatus.HEALTHY


async def test_manager_overall_status_reflects_a_registered_dependency_failure() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")
    manager.registry.dependencies.register("bad", _unhealthy_check)

    assert await manager.overall_status() == HealthStatus.UNHEALTHY


async def test_manager_maintenance_mode_overrides_the_calculated_status() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")
    manager.registry.dependencies.register("bad", _unhealthy_check)

    manager.enter_maintenance()
    assert await manager.overall_status() == HealthStatus.MAINTENANCE

    manager.exit_maintenance()
    assert await manager.overall_status() == HealthStatus.UNHEALTHY


async def test_manager_heartbeat_reflects_service_identity_and_status() -> None:
    manager = MonitoringManager(service_name="gateway", version="2.1.0", environment="prod")

    heartbeat = await manager.heartbeat()

    assert heartbeat.service_name == "gateway"
    assert heartbeat.version == "2.1.0"
    assert heartbeat.environment == "prod"
    assert heartbeat.status == HealthStatus.HEALTHY


async def test_manager_sla_report_reflects_configured_objective() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")

    report = await manager.sla_report()

    assert report.objective == manager.sla_objective


async def test_manager_trigger_alert_reaches_a_registered_sink() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")
    received = []

    async def sink(alert: object) -> None:
        received.append(alert)

    manager.registry.alerts.register_sink(sink)

    await manager.trigger_alert(AlertCategory.HIGH_CPU, ThresholdLevel.CRITICAL, "cpu is very hot")

    assert len(received) == 1


async def test_manager_start_and_stop_delegate_to_the_collector() -> None:
    manager = MonitoringManager(service_name="gateway", version="1.0.0", environment="test")

    await manager.start()
    await asyncio.sleep(0.02)
    await manager.stop()

    assert manager.collector.latest_status is not None


# --- factory.py ---


async def test_create_monitoring_framework_builds_a_ready_manager_and_starts_collection() -> None:
    manager = await create_monitoring_framework(
        service_name="gateway", version="1.0.0", environment="test"
    )

    try:
        assert isinstance(manager, MonitoringManager)
        assert manager.service_name == "gateway"
        await asyncio.sleep(0.02)
        assert manager.collector.latest_status is not None
    finally:
        await manager.stop()


async def test_create_monitoring_framework_can_skip_starting_collection() -> None:
    manager = await create_monitoring_framework(
        service_name="gateway",
        version="1.0.0",
        environment="test",
        start_collection=False,
    )

    assert manager.collector.latest_status == HealthStatus.UNKNOWN
    assert manager.collector.latest_application is None


async def _healthy_check() -> DependencyCheckResult:
    return DependencyCheckResult(name="dep", status=HealthStatus.HEALTHY, latency_ms=1.0)


async def _unhealthy_check() -> DependencyCheckResult:
    return DependencyCheckResult(name="dep", status=HealthStatus.UNHEALTHY, latency_ms=1.0)


async def _raising_check() -> DependencyCheckResult:
    raise RuntimeError("boom")
