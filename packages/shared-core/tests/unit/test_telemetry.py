"""Tests for the OpenTelemetry provider/trace/span primitives."""

from __future__ import annotations

from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.telemetry import configure_tracing, get_tracer, start_root_trace, start_span
from shared_core.telemetry.span import SpanType


def _provider_with_exporter() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_configure_tracing_sets_service_name_resource() -> None:
    _, exporter = _provider_with_exporter()

    provider = configure_tracing(
        service_name="test-service", span_processor=SimpleSpanProcessor(exporter)
    )

    assert provider.resource.attributes["service.name"] == "test-service"


def test_start_span_creates_a_span_with_attributes() -> None:
    provider, exporter = _provider_with_exporter()
    tracer = provider.get_tracer(__name__)

    with start_span(tracer, "do-work", widget_id="123") as span:
        assert span.is_recording()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "do-work"
    attributes = spans[0].attributes
    assert attributes is not None
    assert attributes["widget_id"] == "123"


def test_start_span_tags_the_span_type_attribute() -> None:
    provider, exporter = _provider_with_exporter()
    tracer = provider.get_tracer(__name__)

    with start_span(tracer, "query", span_type=SpanType.DATABASE_QUERY):
        pass

    spans = exporter.get_finished_spans()
    attributes = spans[0].attributes
    assert attributes is not None
    assert attributes["span.type"] == "database_query"


def test_get_tracer_returns_a_usable_tracer() -> None:
    provider, _exporter = _provider_with_exporter()
    trace_api.set_tracer_provider(provider)
    tracer = get_tracer("my.module")

    with tracer.start_as_current_span("span-name") as span:
        assert span.is_recording()


def test_start_root_trace_creates_a_span_with_no_parent() -> None:
    provider, exporter = _provider_with_exporter()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("outer"), start_root_trace(tracer, "root") as span:
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["root"].parent is None
