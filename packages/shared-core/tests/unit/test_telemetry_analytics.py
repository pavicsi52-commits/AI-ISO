"""Tests for analytics.py, against real OpenTelemetry span completion."""

from __future__ import annotations

import time

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode
from shared_core.telemetry.analytics import AnalyticsSpanProcessor, SpanEdge, TraceRecorder


def _provider(service_name: str, recorder: TraceRecorder) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    provider.add_span_processor(AnalyticsSpanProcessor(recorder))
    return provider


def test_analytics_span_processor_records_a_root_trace() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("checkout"):
        pass

    traces = recorder.traces()
    assert len(traces) == 1
    assert traces[0].name == "checkout"
    assert traces[0].service_name == "gateway"
    assert traces[0].is_error is False
    assert traces[0].duration_ms >= 0.0


def test_analytics_span_processor_ignores_non_root_spans_for_trace_summaries() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("outer"), tracer.start_as_current_span("inner"):
        pass

    traces = recorder.traces()
    assert len(traces) == 1
    assert traces[0].name == "outer"


def test_analytics_span_processor_marks_error_status_traces() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("failing-op") as span:
        span.set_status(Status(StatusCode.ERROR))

    traces = recorder.traces()
    assert traces[0].is_error is True


def test_trace_recorder_slowest_traces_orders_by_duration_descending() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("fast"):
        pass
    with tracer.start_as_current_span("slow"):
        time.sleep(0.01)

    slowest = recorder.slowest_traces(n=1)
    assert slowest[0].name == "slow"


def test_trace_recorder_error_hotspots_counts_only_errored_traces() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("ok"):
        pass
    with tracer.start_as_current_span("bad") as span:
        span.set_status(Status(StatusCode.ERROR))
    with tracer.start_as_current_span("bad") as span:
        span.set_status(Status(StatusCode.ERROR))

    hotspots = recorder.error_hotspots()
    assert hotspots == [("bad", 2)]


def test_trace_recorder_percentile_latency_is_zero_with_no_traces() -> None:
    assert TraceRecorder().percentile_latency_ms(95) == 0.0


def test_trace_recorder_percentile_latency_p100_is_the_max_duration() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    for _ in range(5):
        with tracer.start_as_current_span("op"):
            pass

    p100 = recorder.percentile_latency_ms(100)
    max_duration = max(t.duration_ms for t in recorder.traces())
    assert p100 == max_duration


def test_trace_recorder_average_latency_is_zero_with_no_traces() -> None:
    assert TraceRecorder().average_latency_ms() == 0.0


def test_trace_recorder_throughput_counts_traces_within_the_window() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("op"):
        pass

    throughput = recorder.throughput_per_second(window_seconds=60.0)
    assert throughput > 0.0


def test_trace_recorder_throughput_is_zero_with_no_recent_traces() -> None:
    assert TraceRecorder().throughput_per_second() == 0.0


def test_trace_recorder_search_filters_by_name_and_error_status() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("checkout-flow"):
        pass
    with tracer.start_as_current_span("checkout-flow") as span:
        span.set_status(Status(StatusCode.ERROR))
    with tracer.start_as_current_span("unrelated"):
        pass

    by_name = recorder.search(name_contains="checkout")
    errors_only = recorder.search(errors_only=True)

    assert len(by_name) == 2
    assert len(errors_only) == 1
    assert errors_only[0].name == "checkout-flow"


def test_trace_recorder_service_dependency_graph_links_caller_to_callee() -> None:
    recorder = TraceRecorder()
    caller_tracer = _provider("gateway", recorder).get_tracer(__name__)
    callee_tracer = _provider("worker", recorder).get_tracer(__name__)

    with caller_tracer.start_as_current_span("outer"), callee_tracer.start_as_current_span("inner"):
        pass

    graph = recorder.service_dependency_graph()

    assert SpanEdge(from_service="gateway", to_service="worker") in graph


def test_trace_recorder_service_dependency_graph_ignores_same_service_calls() -> None:
    recorder = TraceRecorder()
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    with tracer.start_as_current_span("outer"), tracer.start_as_current_span("inner"):
        pass

    assert recorder.service_dependency_graph() == []


def test_trace_recorder_respects_a_bounded_max_size() -> None:
    recorder = TraceRecorder(max_size=2)
    tracer = _provider("gateway", recorder).get_tracer(__name__)

    for _ in range(5):
        with tracer.start_as_current_span("op"):
            pass

    assert len(recorder.traces()) == 2
