"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes:
every attribute below is asserted on directly out of the exported span,
never inferred from "the context manager did not raise."
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_circuit_transition,
    trace_health_probe,
    trace_proxy_request,
    trace_publish,
    trace_quota_check,
    trace_rate_limit_check,
    trace_route_resolution,
    trace_upstream_call,
    trace_worker_tick,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_proxy_request_carries_method_path_and_route_id(self) -> None:
        tracer, exporter = _tracer()
        with trace_proxy_request(tracer, method="GET", path="/echo", route_id="route-1") as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "gateway.proxy.request"
        attributes = dict(finished[0].attributes or {})
        assert attributes["gateway.method"] == "GET"
        assert attributes["gateway.path"] == "/echo"
        assert attributes["gateway.route_id"] == "route-1"
        assert attributes["span.type"] == "rest_api"

    def test_upstream_call_carries_service_id_and_instance_url(self) -> None:
        tracer, exporter = _tracer()
        with trace_upstream_call(tracer, service_id="svc-1", instance_url="http://backend.test"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.upstream.call"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.service_id"] == "svc-1"
        assert attributes["gateway.instance_url"] == "http://backend.test"
        assert attributes["span.type"] == "rest_api"

    def test_route_resolution_carries_method_path_and_matched(self) -> None:
        tracer, exporter = _tracer()
        with trace_route_resolution(tracer, method="POST", path="/echo", matched=True):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.route.resolve"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.method"] == "POST"
        assert attributes["gateway.path"] == "/echo"
        assert attributes["gateway.matched"] is True
        assert attributes["span.type"] == "background_job"

    def test_route_resolution_carries_matched_false_when_nothing_matches(self) -> None:
        tracer, exporter = _tracer()
        with trace_route_resolution(tracer, method="GET", path="/missing", matched=False):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["gateway.matched"] is False

    def test_rate_limit_check_carries_scope_and_allowed(self) -> None:
        tracer, exporter = _tracer()
        with trace_rate_limit_check(tracer, scope="endpoint", allowed=False):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.ratelimit.check"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.scope"] == "endpoint"
        assert attributes["gateway.allowed"] is False
        assert attributes["span.type"] == "background_job"

    def test_quota_check_carries_scope_kind_and_allowed(self) -> None:
        tracer, exporter = _tracer()
        with trace_quota_check(tracer, scope="client", kind="request", allowed=True):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.quota.check"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.scope"] == "client"
        assert attributes["gateway.kind"] == "request"
        assert attributes["gateway.allowed"] is True
        assert attributes["span.type"] == "background_job"

    def test_circuit_transition_carries_instance_and_both_states(self) -> None:
        tracer, exporter = _tracer()
        with trace_circuit_transition(
            tracer, instance_url="http://backend.test", from_state="closed", to_state="open"
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.circuit.transition"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.instance_url"] == "http://backend.test"
        assert attributes["gateway.from_state"] == "closed"
        assert attributes["gateway.to_state"] == "open"
        assert attributes["span.type"] == "background_job"

    def test_health_probe_carries_instance_and_status_and_nothing_else(self) -> None:
        # Spans carry identifiers and outcomes, never request/response
        # bodies -- checked here against the exact attribute set rather
        # than only the named attributes.
        tracer, exporter = _tracer()
        with trace_health_probe(tracer, instance_url="http://backend.test", status="healthy"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["gateway.instance_url"] == "http://backend.test"
        assert attributes["gateway.status"] == "healthy"
        assert set(attributes) == {"gateway.instance_url", "gateway.status", "span.type"}

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="health_probe_sweep", processed=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.worker"] == "health_probe_sweep"
        assert attributes["gateway.processed"] == 3
        assert attributes["span.type"] == "background_job"

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="GatewayHealthChanged"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "gateway.event.publish"
        attributes = dict(finished.attributes or {})
        assert attributes["gateway.event"] == "GatewayHealthChanged"
        assert attributes["span.type"] == "background_job"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="QuotaExceeded", correlation_id="abc-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["gateway.event"] == "QuotaExceeded"
        assert attributes["correlation_id"] == "abc-123"

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_upstream_call(tracer, service_id="svc-1", instance_url="http://backend.test"),
        ):
            raise RuntimeError("boom")

    def test_the_span_that_raised_is_still_exported(self) -> None:
        # `start_span` uses a plain `with`, not a try/except that
        # swallows -- the span should still end (and export) even
        # though the exception propagates past this helper.
        tracer, exporter = _tracer()
        with (
            pytest.raises(RuntimeError),
            trace_worker_tick(tracer, worker="quota_reset_sweep", processed=0),
        ):
            raise RuntimeError("boom")
        assert len(exporter.get_finished_spans()) == 1
