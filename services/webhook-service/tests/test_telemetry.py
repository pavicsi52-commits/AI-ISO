"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes: every
attribute below is asserted on directly out of the exported span, never
inferred from "the context manager did not raise."
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_delivery,
    trace_publish,
    trace_queue_processing,
    trace_reception,
    trace_replay,
    trace_retry,
    trace_signature_verification,
    trace_transformation,
    trace_worker_tick,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_reception_carries_kind_and_event_type(self) -> None:
        tracer, exporter = _tracer()
        with trace_reception(tracer, kind="incoming", event_type="order.created") as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "webhook.reception"
        attributes = dict(finished[0].attributes or {})
        assert attributes["webhook.kind"] == "incoming"
        assert attributes["webhook.event_type"] == "order.created"
        assert attributes["span.type"] == "rest_api"

    def test_signature_verification_carries_endpoint_and_verified(self) -> None:
        tracer, exporter = _tracer()
        with trace_signature_verification(tracer, endpoint_id="ep-1", verified=True):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.signature.verify"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.endpoint_id"] == "ep-1"
        assert attributes["webhook.verified"] is True
        assert attributes["span.type"] == "rest_api"

    def test_signature_verification_carries_verified_false_and_nothing_else(self) -> None:
        # Spans carry identifiers and outcomes, never payload content --
        # checked here against the exact attribute set, not only the
        # named attributes, so a leak of extra data would fail loudly.
        tracer, exporter = _tracer()
        with trace_signature_verification(tracer, endpoint_id="ep-2", verified=False):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["webhook.endpoint_id"] == "ep-2"
        assert attributes["webhook.verified"] is False
        assert set(attributes) == {"webhook.endpoint_id", "webhook.verified", "span.type"}

    def test_transformation_carries_endpoint_and_kind(self) -> None:
        tracer, exporter = _tracer()
        with trace_transformation(tracer, endpoint_id="ep-1", kind="json_mapping"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.transformation.apply"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.endpoint_id"] == "ep-1"
        assert attributes["webhook.transformation_kind"] == "json_mapping"
        assert attributes["span.type"] == "background_job"

    def test_queue_processing_carries_delivery_and_endpoint(self) -> None:
        tracer, exporter = _tracer()
        with trace_queue_processing(tracer, delivery_id="del-1", endpoint_id="ep-1"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.queue.process"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.delivery_id"] == "del-1"
        assert attributes["webhook.endpoint_id"] == "ep-1"
        assert attributes["span.type"] == "background_job"

    def test_delivery_carries_delivery_endpoint_and_status_code(self) -> None:
        tracer, exporter = _tracer()
        with trace_delivery(tracer, delivery_id="del-1", endpoint_id="ep-1", status_code=200):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.delivery"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.delivery_id"] == "del-1"
        assert attributes["webhook.endpoint_id"] == "ep-1"
        assert attributes["webhook.status_code"] == 200
        assert attributes["span.type"] == "background_job"

    def test_delivery_carries_a_null_status_code_when_the_request_never_completed(self) -> None:
        tracer, exporter = _tracer()
        with trace_delivery(tracer, delivery_id="del-2", endpoint_id="ep-1", status_code=None):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["webhook.delivery_id"] == "del-2"
        assert "webhook.status_code" not in attributes  # OTel drops None-valued attributes

    def test_retry_carries_delivery_and_attempt_number(self) -> None:
        tracer, exporter = _tracer()
        with trace_retry(tracer, delivery_id="del-1", attempt_number=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.retry"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.delivery_id"] == "del-1"
        assert attributes["webhook.attempt_number"] == 3
        assert attributes["span.type"] == "background_job"

    def test_replay_carries_job_id_and_scope(self) -> None:
        tracer, exporter = _tracer()
        with trace_replay(tracer, job_id="job-1", scope="by_event"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.replay"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.job_id"] == "job-1"
        assert attributes["webhook.scope"] == "by_event"
        assert attributes["span.type"] == "background_job"

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="retry_sweep", processed=5):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.worker"] == "retry_sweep"
        assert attributes["webhook.processed"] == 5
        assert attributes["span.type"] == "background_job"

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="WebhookDelivered"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "webhook.event.publish"
        attributes = dict(finished.attributes or {})
        assert attributes["webhook.event"] == "WebhookDelivered"
        assert attributes["span.type"] == "background_job"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="WebhookFailed", correlation_id="abc-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["webhook.event"] == "WebhookFailed"
        assert attributes["correlation_id"] == "abc-123"

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_delivery(tracer, delivery_id="del-1", endpoint_id="ep-1", status_code=None),
        ):
            raise RuntimeError("boom")

    def test_the_span_that_raised_is_still_exported(self) -> None:
        # `start_span` uses a plain `with`, not a try/except that
        # swallows -- the span should still end (and export) even
        # though the exception propagates past this helper.
        tracer, exporter = _tracer()
        with (
            pytest.raises(RuntimeError),
            trace_worker_tick(tracer, worker="replay_processor", processed=0),
        ):
            raise RuntimeError("boom")
        assert len(exporter.get_finished_spans()) == 1
