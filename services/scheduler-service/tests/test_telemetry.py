"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes
(found and fixed in ``services/change-management-service``'s copy of
this file, and confirmed present in every other prior AI-IOS service's
own copy too): every attribute below is asserted on directly out of the
exported span, never inferred from "the context manager did not raise."
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_dispatch,
    trace_execution,
    trace_publish,
    trace_queue_time,
    trace_recovery,
    trace_retry,
    trace_scheduling,
    trace_worker_tick,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_scheduling_carries_job_id_and_trigger_type(self) -> None:
        tracer, exporter = _tracer()
        with trace_scheduling(tracer, job_id="job-1", trigger_type="cron") as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "scheduler.schedule.compute"
        attributes = dict(finished[0].attributes or {})
        assert attributes["scheduler.job_id"] == "job-1"
        assert attributes["scheduler.trigger_type"] == "cron"
        assert attributes["span.type"] == "background_job"

    def test_dispatch_carries_job_id_type_and_trigger_source(self) -> None:
        tracer, exporter = _tracer()
        with trace_dispatch(
            tracer, job_id="job-1", job_type="custom_job", trigger_source="schedule"
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.dispatch"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.job_id"] == "job-1"
        assert attributes["scheduler.job_type"] == "custom_job"
        assert attributes["scheduler.trigger_source"] == "schedule"
        assert attributes["span.type"] == "rest_api"

    def test_queue_time_carries_execution_id_and_queue_seconds(self) -> None:
        tracer, exporter = _tracer()
        with trace_queue_time(tracer, execution_id="exec-1", queue_seconds=4.5):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.queue.wait"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.execution_id"] == "exec-1"
        assert attributes["scheduler.queue_seconds"] == 4.5
        assert attributes["span.type"] == "background_job"

    def test_execution_carries_execution_id_and_status(self) -> None:
        tracer, exporter = _tracer()
        with trace_execution(tracer, execution_id="exec-1", status="completed"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.execution"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.execution_id"] == "exec-1"
        assert attributes["scheduler.status"] == "completed"

    def test_retry_carries_job_id_and_attempt_number(self) -> None:
        tracer, exporter = _tracer()
        with trace_retry(tracer, job_id="job-1", attempt_number=2):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.retry"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.job_id"] == "job-1"
        assert attributes["scheduler.attempt_number"] == 2

    def test_recovery_carries_only_failure_id_and_action_never_error_detail(self) -> None:
        # Only the action taken, never the failure's own error detail --
        # an error message can echo back exactly the sensitive input that
        # caused it, and a span is not where that belongs.
        tracer, exporter = _tracer()
        with trace_recovery(tracer, failure_id="fail-1", recovery_action="manual_recovery"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.recovery"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.failure_id"] == "fail-1"
        assert attributes["scheduler.recovery_action"] == "manual_recovery"
        assert attributes["span.type"] == "rest_api"
        assert set(attributes) == {"scheduler.failure_id", "scheduler.recovery_action", "span.type"}

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="retry_sweep", processed=7):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["scheduler.worker"] == "retry_sweep"
        assert attributes["scheduler.processed"] == 7

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="JobStarted"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "scheduler.event.publish"
        assert dict(finished.attributes or {})["scheduler.event"] == "JobStarted"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="JobCompleted", correlation_id="abc-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["scheduler.event"] == "JobCompleted"
        assert attributes["correlation_id"] == "abc-123"

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_dispatch(tracer, job_id="job-1", job_type="custom_job", trigger_source="manual"),
        ):
            raise RuntimeError("boom")

    def test_a_span_carries_ids_and_counts_never_job_payload(self) -> None:
        # A job's own payload can carry sensitive data specific to
        # whichever platform service actually interprets it -- never
        # passed to a span, only identifiers and counts.
        tracer, exporter = _tracer()
        with trace_dispatch(
            tracer, job_id="job-42", job_type="custom_job", trigger_source="schedule"
        ):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert set(attributes) == {
            "scheduler.job_id",
            "scheduler.job_type",
            "scheduler.trigger_source",
            "span.type",
        }
