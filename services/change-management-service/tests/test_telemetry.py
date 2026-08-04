"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK,
with a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` --
so each finished span's actual name and attributes can be read back and
asserted on, rather than only proving the context manager does not
raise.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from app.telemetry.tracing import (
    trace_approval_decide,
    trace_cab_close,
    trace_change_create,
    trace_change_transition,
    trace_conflict_sweep,
    trace_implementation,
    trace_publish,
    trace_report,
    trace_risk_assessment,
    trace_rollback,
    trace_validation,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_change_create_carries_type_category_and_priority(self) -> None:
        tracer, exporter = _tracer()
        with trace_change_create(
            tracer, change_type="normal", category="application", priority="medium"
        ) as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "change.create"
        attributes = dict(finished[0].attributes or {})
        assert attributes["change.type"] == "normal"
        assert attributes["change.category"] == "application"
        assert attributes["change.priority"] == "medium"
        assert attributes["span.type"] == "rest_api"

    def test_change_transition_carries_from_and_to_status(self) -> None:
        tracer, exporter = _tracer()
        with trace_change_transition(tracer, from_status="draft", to_status="submitted"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.transition"
        attributes = dict(finished.attributes or {})
        assert attributes["change.from_status"] == "draft"
        assert attributes["change.to_status"] == "submitted"

    def test_risk_assessment_carries_level_and_score(self) -> None:
        tracer, exporter = _tracer()
        with trace_risk_assessment(tracer, risk_level="high", automated_score=72.5):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.risk.assess"
        attributes = dict(finished.attributes or {})
        assert attributes["change.risk.level"] == "high"
        assert attributes["change.risk.automated_score"] == 72.5

    def test_approval_decide_carries_level_and_decision(self) -> None:
        tracer, exporter = _tracer()
        with trace_approval_decide(tracer, level=1, decision="approved"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.approval.decide"
        attributes = dict(finished.attributes or {})
        assert attributes["change.approval.level"] == 1
        assert attributes["change.approval.decision"] == "approved"

    def test_cab_close_carries_outcome_quorum_and_votes(self) -> None:
        tracer, exporter = _tracer()
        with trace_cab_close(tracer, outcome="approved", quorum_met=True, votes=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.cab.close"
        attributes = dict(finished.attributes or {})
        assert attributes["change.cab.outcome"] == "approved"
        assert attributes["change.cab.quorum_met"] is True
        assert attributes["change.cab.votes"] == 3

    def test_cab_close_defaults_a_missing_outcome_to_none(self) -> None:
        tracer, exporter = _tracer()
        with trace_cab_close(tracer, outcome=None, quorum_met=False, votes=0):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["change.cab.outcome"] == "none"

    def test_implementation_carries_the_phase(self) -> None:
        tracer, exporter = _tracer()
        with trace_implementation(tracer, phase="start"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.implementation"
        assert dict(finished.attributes or {})["change.implementation.phase"] == "start"

    def test_validation_carries_kind_status_and_gate_flag(self) -> None:
        tracer, exporter = _tracer()
        with trace_validation(tracer, kind="pre_change", status="passed", is_gate=True):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.validation.record"
        attributes = dict(finished.attributes or {})
        assert attributes["change.validation.kind"] == "pre_change"
        assert attributes["change.validation.status"] == "passed"
        assert attributes["change.validation.is_gate"] is True

    def test_rollback_carries_the_phase(self) -> None:
        tracer, exporter = _tracer()
        with trace_rollback(tracer, phase="complete"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.rollback"
        assert dict(finished.attributes or {})["change.rollback.phase"] == "complete"

    def test_conflict_sweep_carries_checked_and_found_counts(self) -> None:
        tracer, exporter = _tracer()
        with trace_conflict_sweep(tracer, changes_checked=12, conflicts_found=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.conflict.sweep"
        assert finished.attributes["span.type"] == "background_job"
        attributes = dict(finished.attributes or {})
        assert attributes["change.conflict.changes_checked"] == 12
        assert attributes["change.conflict.conflicts_found"] == 3

    def test_report_carries_kind_and_row_count_never_rows(self) -> None:
        tracer, exporter = _tracer()
        with trace_report(tracer, kind="change", rows=42):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.report.generate"
        attributes = dict(finished.attributes or {})
        assert attributes["change.report_kind"] == "change"
        assert attributes["change.rows"] == 42

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="ChangeCreated"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "change.event.publish"
        assert dict(finished.attributes or {})["change.event"] == "ChangeCreated"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="ChangeScheduled", correlation_id="abc-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["change.event"] == "ChangeScheduled"
        assert attributes["correlation_id"] == "abc-123"

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_change_create(
                tracer, change_type="normal", category="application", priority="medium"
            ),
        ):
            raise RuntimeError("boom")

    def test_a_span_carries_only_chain_metadata_never_who_decided(self) -> None:
        # Level and decision are chain metadata, not who decided -- an
        # approver's identity belongs in the approval row and the audit
        # trail, not in a span attribute.
        tracer, exporter = _tracer()
        with trace_approval_decide(tracer, level=2, decision="rejected"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert set(attributes) == {
            "change.approval.level",
            "change.approval.decision",
            "span.type",
        }
