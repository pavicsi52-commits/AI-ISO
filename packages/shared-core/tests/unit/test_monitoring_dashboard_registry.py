"""Tests for dashboard.py and registry.py."""

from __future__ import annotations

import json

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.application import capture_application_snapshot
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.dashboard import build_dashboard_payload
from shared_core.monitoring.registry import MonitoringRegistry
from shared_core.monitoring.resources import capture_resource_snapshot
from shared_core.monitoring.thresholds import default_cpu_threshold

# --- dashboard.py ---


def test_build_dashboard_payload_is_a_plain_json_serializable_dict() -> None:
    availability = AvailabilityTracker()
    availability.record(HealthStatus.HEALTHY)

    payload = build_dashboard_payload(
        service_name="gateway",
        status=HealthStatus.HEALTHY,
        application=capture_application_snapshot(),
        resources=capture_resource_snapshot(),
        dependencies=[],
        availability=availability.current_window(),
    )

    assert payload["service"] == "gateway"
    assert payload["status"] == "healthy"
    assert "timestamp" in payload
    assert isinstance(payload["application"], dict)
    assert isinstance(payload["resources"], dict)
    assert payload["dependencies"] == []
    assert isinstance(payload["availability"], dict)


def test_build_dashboard_payload_json_roundtrips() -> None:
    availability = AvailabilityTracker()
    payload = build_dashboard_payload(
        service_name="gateway",
        status=HealthStatus.DEGRADED,
        application=capture_application_snapshot(),
        resources=capture_resource_snapshot(),
        dependencies=[],
        availability=availability.current_window(),
    )

    serialized = json.dumps(payload)
    reloaded = json.loads(serialized)

    assert reloaded["status"] == "degraded"


# --- registry.py ---


def test_monitoring_registry_composes_its_sub_registries_by_default() -> None:
    registry = MonitoringRegistry()

    assert registry.health is not None
    assert registry.deep_health is not None
    assert registry.dependencies is not None
    assert registry.services is not None
    assert registry.alerts is not None


def test_monitoring_registry_register_and_get_threshold_roundtrips() -> None:
    registry = MonitoringRegistry()
    threshold = default_cpu_threshold()

    registry.register_threshold(threshold)

    assert registry.get_threshold("cpu_percent") is threshold


def test_monitoring_registry_get_threshold_returns_none_when_unregistered() -> None:
    assert MonitoringRegistry().get_threshold("nope") is None


def test_monitoring_registry_thresholds_returns_every_registered_threshold() -> None:
    registry = MonitoringRegistry()
    registry.register_threshold(default_cpu_threshold())

    assert set(registry.thresholds()) == {"cpu_percent"}


def test_monitoring_registry_register_and_list_dashboards_roundtrips() -> None:
    registry = MonitoringRegistry()

    registry.register_dashboard("grafana-main", "Primary Grafana overview board")

    assert registry.dashboards() == {"grafana-main": "Primary Grafana overview board"}
