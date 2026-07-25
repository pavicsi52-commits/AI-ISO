"""Tests for services.py and heartbeat.py."""

from __future__ import annotations

import time

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.application import ApplicationStatistics
from shared_core.monitoring.heartbeat import build_heartbeat
from shared_core.monitoring.services import ServiceRegistry

# --- services.py ---


def test_service_registry_report_and_get_roundtrips() -> None:
    registry = ServiceRegistry()

    registry.report("gateway", HealthStatus.HEALTHY, version="1.2.3")

    service = registry.get("gateway")
    assert service is not None
    assert service.name == "gateway"
    assert service.status == HealthStatus.HEALTHY
    assert service.version == "1.2.3"


def test_service_registry_get_returns_none_for_an_unknown_service() -> None:
    assert ServiceRegistry().get("nope") is None


def test_service_registry_all_returns_every_reported_service() -> None:
    registry = ServiceRegistry()
    registry.report("a", HealthStatus.HEALTHY)
    registry.report("b", HealthStatus.DEGRADED)

    names = {service.name for service in registry.all()}

    assert names == {"a", "b"}


def test_service_registry_overall_status_is_the_worst_case() -> None:
    registry = ServiceRegistry()
    registry.report("a", HealthStatus.HEALTHY)
    registry.report("b", HealthStatus.UNHEALTHY)

    assert registry.overall_status() == HealthStatus.UNHEALTHY


def test_service_registry_overall_status_is_healthy_when_nothing_has_reported() -> None:
    assert ServiceRegistry().overall_status() == HealthStatus.HEALTHY


def test_service_registry_report_overwrites_the_previous_report_for_the_same_name() -> None:
    registry = ServiceRegistry()
    registry.report("gateway", HealthStatus.HEALTHY)
    registry.report("gateway", HealthStatus.UNHEALTHY)

    service = registry.get("gateway")
    assert service is not None
    assert service.status == HealthStatus.UNHEALTHY
    assert len(registry.all()) == 1


def test_service_registry_stale_services_finds_services_past_the_max_age() -> None:
    registry = ServiceRegistry()
    registry.report("stale", HealthStatus.HEALTHY)
    time.sleep(0.05)

    stale = registry.stale_services(max_age_seconds=0.01)

    assert [service.name for service in stale] == ["stale"]


def test_service_registry_stale_services_excludes_recently_reported_services() -> None:
    registry = ServiceRegistry()
    registry.report("fresh", HealthStatus.HEALTHY)

    stale = registry.stale_services(max_age_seconds=60.0)

    assert stale == []


# --- heartbeat.py ---


def test_build_heartbeat_captures_service_identity_and_status() -> None:
    heartbeat = build_heartbeat(
        service_name="gateway",
        version="1.0.0",
        environment="test",
        status=HealthStatus.HEALTHY,
        statistics=ApplicationStatistics(),
    )

    assert heartbeat.service_name == "gateway"
    assert heartbeat.version == "1.0.0"
    assert heartbeat.environment == "test"
    assert heartbeat.status == HealthStatus.HEALTHY
    assert heartbeat.hostname


def test_build_heartbeat_uses_an_explicit_hostname_override() -> None:
    heartbeat = build_heartbeat(
        service_name="gateway",
        version="1.0.0",
        environment="test",
        status=HealthStatus.HEALTHY,
        statistics=ApplicationStatistics(),
        hostname="custom-host",
    )

    assert heartbeat.hostname == "custom-host"


def test_build_heartbeat_reflects_request_and_error_counts_from_statistics() -> None:
    stats = ApplicationStatistics()
    stats.record_request(50.0)
    stats.record_request(150.0)
    stats.record_error()

    heartbeat = build_heartbeat(
        service_name="gateway",
        version="1.0.0",
        environment="test",
        status=HealthStatus.HEALTHY,
        statistics=stats,
    )

    assert heartbeat.request_count == 2
    assert heartbeat.error_count == 1
    assert heartbeat.latency_ms == stats.average_response_time_ms
