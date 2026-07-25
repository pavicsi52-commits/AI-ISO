"""Tests for manager.py and factory.py."""

from __future__ import annotations

from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.config.settings import TelemetrySettings
from shared_core.enums.health_status import HealthStatus
from shared_core.telemetry.analytics import TraceRecorder
from shared_core.telemetry.factory import create_telemetry_framework
from shared_core.telemetry.manager import TelemetryManager
from shared_core.telemetry.sampling import DynamicSampler


def _manager() -> tuple[TelemetryManager, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    manager = TelemetryManager(
        service_name="gateway",
        service_version="1.0.0",
        environment="test",
        tracer_provider=provider,
        tracer=tracer,
        recorder=TraceRecorder(),
    )
    return manager, exporter


# --- manager.py ---


def test_manager_start_root_trace_produces_a_parentless_span() -> None:
    manager, exporter = _manager()

    with manager.start_root_trace("checkout") as span:
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["checkout"].parent is None


def test_manager_start_span_attaches_under_the_current_span() -> None:
    manager, exporter = _manager()

    with manager.tracer.start_as_current_span("outer"), manager.start_span("inner") as span:
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["inner"].parent is not None


def test_manager_current_trace_context_reflects_service_identity() -> None:
    manager, _exporter = _manager()

    context = manager.current_trace_context()

    assert context.service_name == "gateway"
    assert context.service_version == "1.0.0"
    assert context.environment == "test"


def test_manager_health_is_healthy_by_default() -> None:
    manager, _exporter = _manager()

    report = manager.health()

    assert report.status == HealthStatus.HEALTHY
    assert report.sampling_rate == 1.0


def test_manager_health_reflects_a_dynamic_samplers_current_ratio() -> None:
    manager, _exporter = _manager()
    manager.sampler = DynamicSampler(initial_ratio=0.25)

    report = manager.health()

    assert report.sampling_rate == 0.25


def test_manager_shutdown_does_not_raise() -> None:
    manager, _exporter = _manager()

    manager.shutdown()


# --- factory.py ---


def test_create_telemetry_framework_builds_a_working_manager() -> None:
    settings = TelemetrySettings(
        telemetry_enabled=True, telemetry_exporter="console", telemetry_sample_ratio=1.0
    )

    manager = create_telemetry_framework(settings, service_version="2.0.0", environment="test")

    try:
        assert manager.service_name == settings.telemetry_service_name
        assert manager.service_version == "2.0.0"
        with manager.start_root_trace("op") as span:
            assert span.is_recording()
    finally:
        manager.shutdown()


def test_create_telemetry_framework_uses_a_json_exporter_when_configured(tmp_path: Path) -> None:
    settings = TelemetrySettings(telemetry_enabled=True, telemetry_exporter="json")
    json_path = tmp_path / "spans.jsonl"

    manager = create_telemetry_framework(settings, json_path=json_path)

    try:
        with manager.start_root_trace("op"):
            pass
        manager.tracer_provider.force_flush()
        assert json_path.exists()
    finally:
        manager.shutdown()


def test_create_telemetry_framework_never_samples_when_disabled() -> None:
    settings = TelemetrySettings(telemetry_enabled=False, telemetry_exporter="console")

    manager = create_telemetry_framework(settings)

    try:
        with manager.start_root_trace("op") as span:
            assert not span.is_recording()
    finally:
        manager.shutdown()
