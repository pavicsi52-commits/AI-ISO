"""Tests for :mod:`app.telemetry.tracing`'s span helpers.

Uses a real ``opentelemetry.sdk.trace.TracerProvider`` with an
in-memory exporter, matching this repository's established telemetry
test pattern.
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_compliance_check,
    trace_configuration_crud,
    trace_drift_detection,
    trace_git_synchronization,
    trace_rollback_operation,
    trace_template_processing,
    trace_version_operation,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_configuration_crud_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_configuration_crud(tracer, operation="create", profile_id="p-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "configuration_management.configuration_crud"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("profile_id") == "p-1"


def test_trace_version_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_version_operation(tracer, operation="snapshot", profile_id="p-1"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "configuration_management.version_operation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "snapshot"


def test_trace_drift_detection() -> None:
    tracer, exporter = _provider()

    with trace_drift_detection(tracer, profile_id="p-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "configuration_management.drift_detection"


def test_trace_compliance_check() -> None:
    tracer, exporter = _provider()

    with trace_compliance_check(tracer, profile_id="p-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "configuration_management.compliance_check"


def test_trace_git_synchronization_includes_provider_attribute() -> None:
    tracer, exporter = _provider()

    with trace_git_synchronization(tracer, provider="github"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "configuration_management.git_synchronization"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("provider") == "github"


def test_trace_template_processing() -> None:
    tracer, exporter = _provider()

    with trace_template_processing(tracer, template_id="t-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "configuration_management.template_processing"


def test_trace_rollback_operation() -> None:
    tracer, exporter = _provider()

    with trace_rollback_operation(tracer, rollback_id="r-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "configuration_management.rollback_operation"


__all__: list[str] = []
