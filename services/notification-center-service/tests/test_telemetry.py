"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes
(first documented in ``services/change-management-service``'s copy of
this file, and confirmed present in every other prior AI-IOS service's
own copy too, but written correctly here from the start): every
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
    trace_acknowledgement,
    trace_api_call,
    trace_delivery,
    trace_publish,
    trace_queue_processing,
    trace_retry,
    trace_template_rendering,
    trace_worker_tick,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_template_rendering_carries_key_and_format(self) -> None:
        tracer, exporter = _tracer()
        with trace_template_rendering(
            tracer, template_key="job.failed", template_format="plain_text"
        ) as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "notification.template.render"
        attributes = dict(finished[0].attributes or {})
        assert attributes["notification.template_key"] == "job.failed"
        assert attributes["notification.template_format"] == "plain_text"
        assert attributes["span.type"] == "background_job"

    def test_queue_processing_carries_notification_id_and_channel(self) -> None:
        tracer, exporter = _tracer()
        with trace_queue_processing(tracer, notification_id="notif-1", channel="email"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.queue.process"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.notification_id"] == "notif-1"
        assert attributes["notification.channel"] == "email"
        assert attributes["span.type"] == "background_job"

    def test_delivery_carries_delivery_id_channel_and_status(self) -> None:
        tracer, exporter = _tracer()
        with trace_delivery(tracer, delivery_id="delivery-1", channel="slack", status="delivered"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.delivery"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.delivery_id"] == "delivery-1"
        assert attributes["notification.channel"] == "slack"
        assert attributes["notification.status"] == "delivered"
        assert attributes["span.type"] == "background_job"

    def test_retry_carries_delivery_id_and_attempt_number(self) -> None:
        tracer, exporter = _tracer()
        with trace_retry(tracer, delivery_id="delivery-1", attempt_number=2):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.retry"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.delivery_id"] == "delivery-1"
        assert attributes["notification.attempt_number"] == 2
        assert attributes["span.type"] == "background_job"

    def test_acknowledgement_carries_only_notification_id_never_body(self) -> None:
        # Spans carry identifiers, channels, and statuses, never
        # notification content -- a recipient-specific body/subject has
        # different retention and access rules than this service's own
        # database.
        tracer, exporter = _tracer()
        with trace_acknowledgement(tracer, notification_id="notif-1"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.acknowledge"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.notification_id"] == "notif-1"
        assert attributes["span.type"] == "rest_api"
        assert set(attributes) == {"notification.notification_id", "span.type"}

    def test_api_call_carries_the_route(self) -> None:
        tracer, exporter = _tracer()
        with trace_api_call(tracer, route="/notifications/send"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.api.call"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.route"] == "/notifications/send"
        assert attributes["span.type"] == "rest_api"

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="retry_sweep", processed=7):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.worker"] == "retry_sweep"
        assert attributes["notification.processed"] == 7
        assert attributes["span.type"] == "background_job"

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="NotificationSent"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "notification.event.publish"
        attributes = dict(finished.attributes or {})
        assert attributes["notification.event"] == "NotificationSent"
        assert attributes["span.type"] == "background_job"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="NotificationFailed", correlation_id="abc-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["notification.event"] == "NotificationFailed"
        assert attributes["correlation_id"] == "abc-123"

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_delivery(tracer, delivery_id="delivery-1", channel="webhook", status="failed"),
        ):
            raise RuntimeError("boom")

    def test_a_span_carries_ids_channels_and_statuses_never_notification_content(self) -> None:
        # The same "no notification body/subject on a span" rule,
        # checked against the exact attribute set this time rather than
        # only the acknowledgement span's.
        tracer, exporter = _tracer()
        with trace_delivery(tracer, delivery_id="delivery-1", channel="webhook", status="failed"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert set(attributes) == {
            "notification.delivery_id",
            "notification.channel",
            "notification.status",
            "span.type",
        }
