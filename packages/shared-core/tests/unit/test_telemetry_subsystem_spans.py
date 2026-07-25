"""Tests for the ten thin per-subsystem span helpers.

queue.py, database.py, cache.py, storage.py, connector.py, plugin.py,
workflow.py, automation.py, validation.py, ai.py -- all built on the
same :func:`shared_core.telemetry.span.start_span` primitive, so one
shared test file covers the pattern once instead of ten near-identical
files.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.ai import trace_ai_request, trace_model_inference
from shared_core.telemetry.automation import trace_automation_step
from shared_core.telemetry.cache import trace_cache_access
from shared_core.telemetry.connector import trace_connector_execution
from shared_core.telemetry.database import trace_database_query
from shared_core.telemetry.plugin import trace_plugin_execution
from shared_core.telemetry.propagation import (
    extract_context,
    inject_context,
    restore_context,
    use_context,
)
from shared_core.telemetry.queue import trace_queue_consume, trace_queue_publish
from shared_core.telemetry.storage import trace_file_download, trace_file_upload
from shared_core.telemetry.validation import trace_validation_step
from shared_core.telemetry.workflow import trace_workflow_step


@pytest.fixture
def tracer_and_exporter() -> Iterator[tuple[Tracer, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider.get_tracer(__name__), exporter


def _case(
    label: str, make_span: Callable[[Tracer], AbstractContextManager[Span]]
) -> tuple[str, Callable[[Tracer], AbstractContextManager[Span]], str]:
    return (label, make_span, label)


def _cases() -> list[tuple[str, Callable[[Tracer], AbstractContextManager[Span]], str]]:
    return [
        _case("queue_publish", lambda t: trace_queue_publish(t, "orders")),
        _case("queue_consume", lambda t: trace_queue_consume(t, "orders")),
        _case("database_query", lambda t: trace_database_query(t, "select", table="users")),
        _case("cache_access", lambda t: trace_cache_access(t, "get", key="user:1")),
        _case("file_upload", lambda t: trace_file_upload(t, "report.csv")),
        _case("file_download", lambda t: trace_file_download(t, "report.csv")),
        _case("connector_execution", lambda t: trace_connector_execution(t, "jira")),
        _case("plugin_execution", lambda t: trace_plugin_execution(t, "slack-notify")),
        _case("workflow_step", lambda t: trace_workflow_step(t, "onboarding", "send-email")),
        _case("automation_step", lambda t: trace_automation_step(t, "cleanup", "purge-temp")),
        _case("validation_step", lambda t: trace_validation_step(t, "email-format")),
        _case("ai_request", lambda t: trace_ai_request(t, "anthropic")),
        _case("model_inference", lambda t: trace_model_inference(t, "claude-5")),
    ]


@pytest.mark.parametrize("label,make_span,expected_type", _cases(), ids=[c[0] for c in _cases()])
def test_subsystem_span_helper_produces_a_recorded_span_with_the_right_type(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
    label: str,
    make_span: Callable[[Tracer], AbstractContextManager[Span]],
    expected_type: str,
) -> None:
    tracer, exporter = tracer_and_exporter

    with make_span(tracer) as span:
        assert isinstance(span, Span)
        assert span.is_recording()

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    attributes = finished[0].attributes
    assert attributes is not None
    assert attributes["span.type"] == expected_type


def test_database_query_without_a_table_omits_the_table_attribute(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_and_exporter

    with trace_database_query(tracer, "ping"):
        pass

    finished = exporter.get_finished_spans()
    attributes = finished[0].attributes
    assert attributes is not None
    assert "db.table" not in attributes


def test_database_query_with_a_table_sets_the_table_attribute(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_and_exporter

    with trace_database_query(tracer, "select", table="orders"):
        pass

    finished = exporter.get_finished_spans()
    attributes = finished[0].attributes
    assert attributes is not None
    assert attributes["db.table"] == "orders"


def test_subsystem_span_helpers_mask_sensitive_extra_attributes(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_and_exporter

    with trace_connector_execution(tracer, "jira", api_key="sk-live-123"):
        pass

    finished = exporter.get_finished_spans()
    attributes = finished[0].attributes
    assert attributes is not None
    assert attributes["api_key"] == "***MASKED***"


def test_trace_queue_publish_injects_trace_context_into_headers(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, _exporter = tracer_and_exporter
    headers: dict[str, str] = {}

    with trace_queue_publish(tracer, "orders", headers=headers) as span:
        expected_trace_id = span.get_span_context().trace_id

    assert headers  # something was actually injected
    extracted = extract_context(headers)
    token = use_context(extracted)
    try:
        with tracer.start_as_current_span("downstream") as downstream_span:
            assert downstream_span.get_span_context().trace_id == expected_trace_id
    finally:
        restore_context(token)


def test_trace_queue_consume_continues_the_publishers_trace_from_headers(
    tracer_and_exporter: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, _exporter = tracer_and_exporter
    headers: dict[str, str] = {}

    with tracer.start_as_current_span("publisher") as publisher_span:
        expected_trace_id = publisher_span.get_span_context().trace_id
        inject_context(headers)

    with trace_queue_consume(tracer, "orders", headers=headers) as span:
        assert span.get_span_context().trace_id == expected_trace_id
