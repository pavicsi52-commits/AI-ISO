"""Tests for propagation.py, worker.py, scheduler.py, and workflow.py's root trace."""

from __future__ import annotations

from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.telemetry.propagation import (
    extract_context,
    inject_context,
    restore_context,
    use_context,
)
from shared_core.telemetry.scheduler import trace_scheduler_job
from shared_core.telemetry.worker import trace_background_job
from shared_core.telemetry.workflow import trace_workflow_execution


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


# --- propagation.py ---


def test_inject_then_extract_context_roundtrips_the_same_trace() -> None:
    provider, _exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("publisher") as publisher_span:
        expected_trace_id = publisher_span.get_span_context().trace_id
        carrier: dict[str, str] = {}
        inject_context(carrier)

    assert carrier  # something was actually written

    extracted = extract_context(carrier)
    token = use_context(extracted)
    try:
        with tracer.start_as_current_span("consumer") as consumer_span:
            assert consumer_span.get_span_context().trace_id == expected_trace_id
    finally:
        restore_context(token)


def test_inject_context_without_an_active_span_produces_an_empty_carrier() -> None:
    carrier = inject_context()

    assert carrier == {}


def test_extract_context_on_an_empty_carrier_yields_no_active_span() -> None:
    context = extract_context({})
    token = use_context(context)
    try:
        assert not trace_api.get_current_span().get_span_context().is_valid
    finally:
        restore_context(token)


# --- worker.py ---


def test_trace_background_job_with_no_carrier_starts_a_parentless_trace() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with (
        tracer.start_as_current_span("unrelated"),
        trace_background_job(tracer, "send-emails") as span,
    ):
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["job.send-emails"].parent is None


def test_trace_background_job_with_a_carrier_continues_the_publishers_trace() -> None:
    provider, _exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("enqueue") as enqueue_span:
        expected_trace_id = enqueue_span.get_span_context().trace_id
        carrier = inject_context()

    with trace_background_job(tracer, "send-emails", carrier=carrier) as span:
        assert span.get_span_context().trace_id == expected_trace_id


# --- scheduler.py ---


def test_trace_scheduler_job_with_no_carrier_starts_a_parentless_trace() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with trace_scheduler_job(tracer, "nightly-report") as span:
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["scheduler.nightly-report"].parent is None


def test_trace_scheduler_job_with_a_carrier_continues_the_original_trace() -> None:
    provider, _exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("schedule-setup") as setup_span:
        expected_trace_id = setup_span.get_span_context().trace_id
        carrier = inject_context()

    with trace_scheduler_job(tracer, "nightly-report", carrier=carrier) as span:
        assert span.get_span_context().trace_id == expected_trace_id


# --- workflow.py root trace ---


def test_trace_workflow_execution_starts_a_parentless_trace() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)

    with (
        tracer.start_as_current_span("unrelated"),
        trace_workflow_execution(tracer, "onboarding") as span,
    ):
        assert span.is_recording()

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["workflow.onboarding"].parent is None
