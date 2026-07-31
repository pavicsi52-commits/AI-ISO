"""Compliance telemetry (docs/051 "TELEMETRY").

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for compliance work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Spans carry shapes and counts, never evidence.** An evidence payload
is a configuration snapshot of somebody's production estate: hostnames,
account lists, network topology, cipher suites. It is stored
deliberately and access-controlled deliberately. A tracing backend has
different retention and different access rules, so putting any of it in
a span attribute would route protected data somewhere it was never meant
to go -- and unlike a database row, a span cannot be redacted after the
fact.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_assessment(
    tracer: Tracer,
    *,
    assessment_id: str,
    scope: str,
    controls: int,
    targets: int,
    **attributes: object,
) -> Iterator[Span]:
    """Span one assessment run.

    Records how much was evaluated, which is what makes a slow run
    diagnosable: 2,000 controls across 5,000 hosts is ten million
    verdicts, and knowing the multiplier is the difference between "the
    database is slow" and "somebody widened the scope".
    """
    with start_span(
        tracer,
        "compliance.assessment.run",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "compliance.assessment_id": assessment_id,
            "compliance.scope": scope,
            "compliance.controls": controls,
            "compliance.targets": targets,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_control_evaluation(
    tracer: Tracer, *, control_code: str, severity: str, **attributes: object
) -> Iterator[Span]:
    """Span one control's evaluation.

    The control *code* is safe to record -- it comes from a published
    standard. The evidence it was evaluated against is not.
    """
    with start_span(
        tracer,
        "compliance.control.evaluate",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "compliance.control_code": control_code,
            "compliance.severity": severity,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_evidence_collection(
    tracer: Tracer, *, kind: str, source: str, size_bytes: int, **attributes: object
) -> Iterator[Span]:
    """Span one evidence write. Size and kind, never content."""
    with start_span(
        tracer,
        "compliance.evidence.collect",
        span_type=SpanType.REST_API,
        attributes={
            "compliance.evidence_kind": kind,
            "compliance.evidence_source": source,
            "compliance.size_bytes": size_bytes,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_scoring(
    tracer: Tracer, *, assessment_id: str, results: int, **attributes: object
) -> Iterator[Span]:
    """Span a scoring pass."""
    with start_span(
        tracer,
        "compliance.scoring.compute",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "compliance.assessment_id": assessment_id,
            "compliance.results": results,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_risk_calculation(
    tracer: Tracer, *, likelihood: str, impact: str, **attributes: object
) -> Iterator[Span]:
    """Span a risk scoring.

    Likelihood and impact are members of a published 5x5 matrix, so
    recording them says nothing about the organization beyond what the
    matrix already says.
    """
    with start_span(
        tracer,
        "compliance.risk.calculate",
        span_type=SpanType.REST_API,
        attributes={
            "compliance.likelihood": likelihood,
            "compliance.impact": impact,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_report(tracer: Tracer, *, kind: str, rows: int, **attributes: object) -> Iterator[Span]:
    """Span a report build.

    Row count, never rows: a report body is exactly the compliance detail
    somebody is entitled to see in one system and not in another.
    """
    with start_span(
        tracer,
        "compliance.report.generate",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "compliance.report_kind": kind,
            "compliance.rows": rows,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "compliance.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"compliance.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_assessment",
    "trace_control_evaluation",
    "trace_evidence_collection",
    "trace_publish",
    "trace_report",
    "trace_risk_calculation",
    "trace_scoring",
]
