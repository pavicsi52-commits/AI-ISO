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
    trace_approval,
    trace_downloads,
    trace_publishing,
    trace_repository_access,
    trace_search,
    trace_validation,
    trace_version_operation,
)


def _provider() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(__name__), exporter


def test_trace_repository_access_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_repository_access(tracer, operation="create", playbook_id="p-1"):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "playbook.repository_access"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "create"
    assert spans[0].attributes.get("playbook_id") == "p-1"


def test_trace_validation() -> None:
    tracer, exporter = _provider()

    with trace_validation(tracer, content_type="shell_script"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "playbook.validation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("content_type") == "shell_script"


def test_trace_approval_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_approval(tracer, operation="decide"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "playbook.approval"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "decide"


def test_trace_publishing() -> None:
    tracer, exporter = _provider()

    with trace_publishing(tracer, playbook_id="p-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "playbook.publishing"


def test_trace_search() -> None:
    tracer, exporter = _provider()

    with trace_search(tracer, query="deploy"):
        pass

    assert exporter.get_finished_spans()[0].name == "playbook.search"


def test_trace_downloads() -> None:
    tracer, exporter = _provider()

    with trace_downloads(tracer, playbook_id="p-1"):
        pass

    assert exporter.get_finished_spans()[0].name == "playbook.downloads"


def test_trace_version_operation_includes_operation_attribute() -> None:
    tracer, exporter = _provider()

    with trace_version_operation(tracer, operation="diff"):
        pass

    spans = exporter.get_finished_spans()
    assert spans[0].name == "playbook.version_operation"
    assert spans[0].attributes is not None
    assert spans[0].attributes.get("operation") == "diff"


__all__: list[str] = []
