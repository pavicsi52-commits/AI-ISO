"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes:
``start_span``'s own signature is ``start_span(tracer, name, *,
span_type=None, **attributes)`` -- there is no parameter actually named
``attributes``, only that catch-all, and a call site that passed one
anyway would silently drop every attribute onto the floor instead of
raising. Every attribute asserted below is read directly out of the
exported span, never inferred from "the context manager did not raise."
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer
from shared_core.telemetry.constants import MASKED_ATTRIBUTE_VALUE

from app.telemetry.tracing import (
    trace_authentication,
    trace_connector_call,
    trace_flow_run,
    trace_health_check,
    trace_marketplace_operation,
    trace_publish,
    trace_routing,
    trace_synchronization,
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
    def test_connector_call_carries_connector_id_and_operation(self) -> None:
        tracer, exporter = _tracer()
        with trace_connector_call(tracer, connector_id="conn-1", operation="fetch_records") as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "hub.connector.call"
        attributes = dict(finished[0].attributes or {})
        assert attributes["hub.connector_id"] == "conn-1"
        assert attributes["hub.operation"] == "fetch_records"
        assert attributes["span.type"] == "rest_api"

    def test_authentication_carries_connector_auth_method_and_succeeded(self) -> None:
        tracer, exporter = _tracer()
        with trace_authentication(
            tracer, connector_id="conn-1", auth_method="oauth2", succeeded=True
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.authentication"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.connector_id"] == "conn-1"
        assert attributes["hub.auth_method"] == "oauth2"
        assert attributes["hub.succeeded"] is True
        assert attributes["span.type"] == "rest_api"

    def test_authentication_carries_succeeded_false_and_nothing_else(self) -> None:
        # Spans carry identifiers and outcomes, never credential content --
        # checked here against the exact attribute set, not only the named
        # attributes, so a leak of extra data would fail loudly.
        tracer, exporter = _tracer()
        with trace_authentication(
            tracer, connector_id="conn-2", auth_method="api_key", succeeded=False
        ):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["hub.connector_id"] == "conn-2"
        assert attributes["hub.auth_method"] == "api_key"
        assert attributes["hub.succeeded"] is False
        assert set(attributes) == {
            "hub.connector_id",
            "hub.auth_method",
            "hub.succeeded",
            "span.type",
        }

    def test_synchronization_carries_sync_job_connector_and_mode(self) -> None:
        tracer, exporter = _tracer()
        with trace_synchronization(
            tracer, sync_job_id="sync-1", connector_id="conn-1", mode="incremental"
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.synchronization"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.sync_job_id"] == "sync-1"
        assert attributes["hub.connector_id"] == "conn-1"
        assert attributes["hub.mode"] == "incremental"
        assert attributes["span.type"] == "background_job"

    def test_transformation_carries_connector_id_and_kind(self) -> None:
        tracer, exporter = _tracer()
        with trace_transformation(tracer, connector_id="conn-1", kind="json_mapping"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.transformation.apply"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.connector_id"] == "conn-1"
        assert attributes["hub.transformation_kind"] == "json_mapping"
        assert attributes["span.type"] == "background_job"

    def test_routing_carries_event_type_and_destinations_matched(self) -> None:
        tracer, exporter = _tracer()
        with trace_routing(tracer, event_type="order.created", destinations_matched=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.routing.resolve"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.event_type"] == "order.created"
        assert attributes["hub.destinations_matched"] == 3
        assert attributes["span.type"] == "background_job"

    def test_routing_carries_zero_destinations_matched(self) -> None:
        # `0` is falsy but must still be present, distinguishing "no
        # destination matched" from "field never set."
        tracer, exporter = _tracer()
        with trace_routing(tracer, event_type="order.cancelled", destinations_matched=0):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["hub.destinations_matched"] == 0

    def test_health_check_carries_connector_id_and_status(self) -> None:
        tracer, exporter = _tracer()
        with trace_health_check(tracer, connector_id="conn-1", status="healthy"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.health.check"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.connector_id"] == "conn-1"
        assert attributes["hub.status"] == "healthy"
        assert attributes["span.type"] == "background_job"

    def test_marketplace_operation_carries_slug_and_operation(self) -> None:
        tracer, exporter = _tracer()
        with trace_marketplace_operation(tracer, slug="salesforce-connector", operation="install"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.marketplace.operation"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.slug"] == "salesforce-connector"
        assert attributes["hub.operation"] == "install"
        assert attributes["span.type"] == "rest_api"

    def test_flow_run_carries_flow_id_status_and_steps_executed(self) -> None:
        tracer, exporter = _tracer()
        with trace_flow_run(tracer, flow_id="flow-1", status="completed", steps_executed=4):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.flow.run"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.flow_id"] == "flow-1"
        assert attributes["hub.status"] == "completed"
        assert attributes["hub.steps_executed"] == 4
        assert attributes["span.type"] == "background_job"

    def test_flow_run_carries_zero_steps_executed(self) -> None:
        tracer, exporter = _tracer()
        with trace_flow_run(tracer, flow_id="flow-2", status="failed", steps_executed=0):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["hub.steps_executed"] == 0

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="sync_scheduler", processed=7):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.worker"] == "sync_scheduler"
        assert attributes["hub.processed"] == 7
        assert attributes["span.type"] == "background_job"

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="ConnectorSynced"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "hub.event.publish"
        attributes = dict(finished.attributes or {})
        assert attributes["hub.event"] == "ConnectorSynced"
        assert attributes["span.type"] == "background_job"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="ConnectorSyncFailed", correlation_id="corr-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["hub.event"] == "ConnectorSyncFailed"
        assert attributes["correlation_id"] == "corr-123"

    def test_extra_attribute_with_a_sensitive_looking_key_is_masked(self) -> None:
        # `start_span` runs every attribute through
        # `shared_core.telemetry.span.sanitize_attributes` before it ever
        # reaches the span -- proof this module's own extra ``**attributes``
        # pass-through actually flows through that masking, not just that
        # the named `hub.*` attributes happen to look safe.
        tracer, exporter = _tracer()
        with trace_connector_call(
            tracer, connector_id="conn-1", operation="authenticate", api_key="super-secret-value"
        ):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["api_key"] == MASKED_ATTRIBUTE_VALUE
        assert "super-secret-value" not in attributes.values()

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_connector_call(tracer, connector_id="conn-1", operation="fetch_records"),
        ):
            raise RuntimeError("boom")

    def test_the_span_that_raised_is_still_exported(self) -> None:
        # `start_span` uses a plain `with`, not a try/except that
        # swallows -- the span should still end (and export) even though
        # the exception propagates past this helper.
        tracer, exporter = _tracer()
        with (
            pytest.raises(RuntimeError),
            trace_worker_tick(tracer, worker="retry_sweep", processed=0),
        ):
            raise RuntimeError("boom")
        assert len(exporter.get_finished_spans()) == 1
