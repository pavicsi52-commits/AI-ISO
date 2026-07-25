"""Tests for configuration.py, storage.py, telemetry.py, metrics.py,
audit.py, and health.py.
"""

from __future__ import annotations

import uuid

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.enums.health_status import HealthStatus
from shared_core.plugins import audit
from shared_core.plugins import metrics as plugin_metrics
from shared_core.plugins.configuration import PluginConfigurationStore, validate_configuration
from shared_core.plugins.exceptions import InvalidManifestError
from shared_core.plugins.health import build_framework_health_report, build_plugin_health_report
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.registry import PluginRegistry
from shared_core.plugins.storage import PluginStorage
from shared_core.plugins.telemetry import (
    trace_plugin_execution,
    trace_plugin_hook,
    trace_plugin_lifecycle,
    trace_plugin_load,
)
from shared_core.storage.wrapper import StorageWrapper


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _manifest(plugin_id: str = "sample") -> PluginManifest:
    return PluginManifest(
        metadata=PluginMetadata(
            plugin_id=plugin_id, name="Sample", version="1.0.0", category=PluginType.AUTOMATION
        ),
        entry_point="sample.plugin:SamplePlugin",
    )


# --- configuration.py ---


def test_validate_configuration_fills_in_defaults() -> None:
    schema = {"retries": {"type": "integer", "default": 3}}

    resolved = validate_configuration({}, schema)

    assert resolved == {"retries": 3}


def test_validate_configuration_raises_for_missing_required_field() -> None:
    schema = {"api_key": {"type": "string", "required": True}}

    with pytest.raises(InvalidManifestError):
        validate_configuration({}, schema)


def test_validate_configuration_raises_for_wrong_type() -> None:
    schema = {"retries": {"type": "integer"}}

    with pytest.raises(InvalidManifestError):
        validate_configuration({"retries": "not-a-number"}, schema)


def test_validate_configuration_passes_through_a_valid_value() -> None:
    schema = {"retries": {"type": "integer"}}

    resolved = validate_configuration({"retries": 5}, schema)

    assert resolved == {"retries": 5}


def test_configuration_store_set_then_get_round_trips() -> None:
    store = PluginConfigurationStore()

    store.set("sample", {"retries": 5})

    assert store.get("sample") == {"retries": 5}


def test_configuration_store_get_returns_empty_dict_when_unset() -> None:
    store = PluginConfigurationStore()

    assert store.get("missing") == {}


def test_configuration_store_set_validates_against_a_schema() -> None:
    store = PluginConfigurationStore()

    with pytest.raises(InvalidManifestError):
        store.set("sample", {}, schema={"api_key": {"type": "string", "required": True}})


# --- storage.py ---


async def test_plugin_storage_scopes_keys_under_a_plugin_prefix(storage: StorageWrapper) -> None:
    plugin_storage = PluginStorage("sample-plugin", storage)
    key = f"file-{uuid.uuid4().hex}.txt"

    await plugin_storage.upload("test-bucket", key, b"hello", "text/plain")

    assert plugin_storage.scoped_key(key) == f"plugins/sample-plugin/{key}"
    assert await plugin_storage.exists("test-bucket", key) is True
    downloaded = await plugin_storage.download("test-bucket", key)
    assert downloaded == b"hello"

    await plugin_storage.delete("test-bucket", key)
    assert await plugin_storage.exists("test-bucket", key) is False


# --- telemetry.py ---


def test_trace_plugin_load_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_plugin_load(tracer, "sample"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_plugin_hook_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_plugin_hook(tracer, "sample", "before_startup"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_plugin_lifecycle_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_plugin_lifecycle(tracer, "sample", "started"):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_trace_plugin_execution_is_reexported() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_plugin_execution(tracer, "sample"):
        pass

    assert len(exporter.get_finished_spans()) == 1


# --- metrics.py ---


def test_record_installed_and_running_set_gauges() -> None:
    plugin_metrics.record_installed(3)
    plugin_metrics.record_running(1)

    assert plugin_metrics.plugins_installed_total._value.get() == 3
    assert plugin_metrics.plugins_running_total._value.get() == 1


def test_record_failure_increments() -> None:
    before = plugin_metrics.plugin_failures_total.labels(plugin_id="sample")._value.get()

    plugin_metrics.record_failure("sample")

    after = plugin_metrics.plugin_failures_total.labels(plugin_id="sample")._value.get()
    assert after == before + 1


def test_record_memory_hook_and_extension_counts() -> None:
    plugin_metrics.record_memory_usage(128.5)
    plugin_metrics.record_hook_count(4)
    plugin_metrics.record_extension_count(7)

    assert plugin_metrics.plugin_memory_usage_mb._value.get() == 128.5
    assert plugin_metrics.plugin_hook_count._value.get() == 4
    assert plugin_metrics.plugin_extension_count._value.get() == 7


def test_measure_execution_observes_duration_on_success() -> None:
    with plugin_metrics.measure_execution("sample"):
        pass  # doesn't raise


def test_measure_execution_records_failure_and_reraises() -> None:
    with pytest.raises(RuntimeError), plugin_metrics.measure_execution("sample"):
        raise RuntimeError("boom")


# --- audit.py ---


def test_audit_functions_do_not_raise() -> None:
    audit.audit_plugin_installed("sample")
    audit.audit_plugin_enabled("sample")
    audit.audit_plugin_disabled("sample")
    audit.audit_plugin_updated("sample", from_version="1.0.0", to_version="2.0.0")
    audit.audit_plugin_uninstalled("sample")
    audit.audit_permission_change("sample", permissions=["network"])
    audit.audit_configuration_change("sample")
    audit.audit_plugin_failure("sample", error="boom")
    audit.audit_security_event("sample", detail="sandbox violation")


def test_audit_all_exports_every_function() -> None:
    assert set(audit.__all__) == {
        "audit_configuration_change",
        "audit_permission_change",
        "audit_plugin_disabled",
        "audit_plugin_enabled",
        "audit_plugin_failure",
        "audit_plugin_installed",
        "audit_plugin_uninstalled",
        "audit_plugin_updated",
        "audit_security_event",
    }


# --- health.py ---


def test_build_plugin_health_report_healthy_for_a_normal_state() -> None:
    report = build_plugin_health_report("sample", PluginState.STARTED)

    assert report.status == HealthStatus.HEALTHY


def test_build_plugin_health_report_unhealthy_when_failed() -> None:
    report = build_plugin_health_report("sample", PluginState.FAILED, error="boom")

    assert report.status == HealthStatus.UNHEALTHY
    assert report.error == "boom"


def test_build_framework_health_report_rolls_up_worst_case() -> None:
    registry = PluginRegistry()
    healthy_record = registry.register(_manifest("healthy-plugin"))
    healthy_record.lifecycle.transition(PluginState.VALIDATED)
    failed_record = registry.register(_manifest("failed-plugin"))
    failed_record.lifecycle.transition(PluginState.FAILED)

    report = build_framework_health_report(registry)

    assert report.status == HealthStatus.UNHEALTHY
    assert report.installed_count == 2
    assert report.failed_count == 1


def test_build_framework_health_report_is_unknown_for_an_empty_registry() -> None:
    report = build_framework_health_report(PluginRegistry())

    assert report.status == HealthStatus.UNKNOWN
    assert report.installed_count == 0
