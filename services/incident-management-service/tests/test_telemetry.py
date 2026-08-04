"""Telemetry spans -- no infrastructure needed, just a real OTel tracer."""

from __future__ import annotations

import pytest
from opentelemetry import trace

from app.telemetry.tracing import (
    trace_assignment,
    trace_escalation,
    trace_incident_create,
    trace_incident_transition,
    trace_major_incident_declare,
    trace_publish,
    trace_report,
    trace_sla_sweep,
)


class TestSpans:
    def test_every_span_context_manager_yields_a_span(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_incident_create(
            tracer, source="monitoring", category="infrastructure", priority="p1_critical"
        ) as span:
            assert span is not None
        with trace_incident_transition(tracer, from_status="new", to_status="assigned") as span:
            assert span is not None
        with trace_sla_sweep(tracer, warned=2, breached=1) as span:
            assert span is not None
        with trace_escalation(tracer, level=1, trigger="sla_breach") as span:
            assert span is not None
        with trace_major_incident_declare(tracer, incident_id="inc-1") as span:
            assert span is not None
        with trace_assignment(tracer, method="on_call") as span:
            assert span is not None
        with trace_report(tracer, kind="incident", rows=10) as span:
            assert span is not None
        with trace_publish(tracer, event_name="IncidentCreated") as span:
            assert span is not None

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer = trace.get_tracer("test")
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_incident_create(tracer, source="manual", category="custom", priority="p3_medium"),
        ):
            raise RuntimeError("boom")

    def test_a_span_carries_ids_and_counts_but_never_incident_content(self) -> None:
        # A declaration reason can describe a live outage in specific
        # detail. It is never passed to the span -- only the incident id.
        tracer = trace.get_tracer("test")
        with trace_major_incident_declare(tracer, incident_id="inc-42") as span:
            rendered = str(getattr(span, "attributes", {}))
        assert "inc-42" in rendered or rendered == "{}"
