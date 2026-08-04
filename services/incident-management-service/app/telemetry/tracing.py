"""Incident management telemetry (docs/052 "TELEMETRY").

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for incident work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Spans carry identifiers and counts, never incident content.** A
title, description, or shared war-room note can describe a live
production outage in specific, sometimes sensitive detail. It is stored
deliberately and access-controlled deliberately; a tracing backend has
different retention and different access rules, so putting any of it in
a span attribute would route that detail somewhere it was never meant
to go -- and unlike a database row, a span cannot be redacted after the
fact.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_incident_create(
    tracer: Tracer, *, source: str, category: str, priority: str, **attributes: object
) -> Iterator[Span]:
    """Span opening one incident."""
    with start_span(
        tracer,
        "incident.create",
        span_type=SpanType.REST_API,
        attributes={
            "incident.source": source,
            "incident.category": category,
            "incident.priority": priority,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_incident_transition(
    tracer: Tracer, *, from_status: str, to_status: str, **attributes: object
) -> Iterator[Span]:
    """Span a status transition."""
    with start_span(
        tracer,
        "incident.transition",
        span_type=SpanType.REST_API,
        attributes={
            "incident.from_status": from_status,
            "incident.to_status": to_status,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_sla_sweep(
    tracer: Tracer, *, warned: int, breached: int, **attributes: object
) -> Iterator[Span]:
    """Span one SLA sweep tick."""
    with start_span(
        tracer,
        "incident.sla.sweep",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"incident.sla.warned": warned, "incident.sla.breached": breached, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_escalation(
    tracer: Tracer, *, level: int, trigger: str, **attributes: object
) -> Iterator[Span]:
    """Span one escalation firing.

    Level and trigger are policy metadata, not who was paged -- a
    responder's identity belongs in the notification it drives, not in
    a span attribute.
    """
    with start_span(
        tracer,
        "incident.escalation.fire",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "incident.escalation.level": level,
            "incident.escalation.trigger": trigger,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_major_incident_declare(
    tracer: Tracer, *, incident_id: str, **attributes: object
) -> Iterator[Span]:
    """Span declaring an incident major.

    Only the incident's id, never its declaration reason -- the reason
    is exactly the sensitive operational detail a span must not carry.
    """
    with start_span(
        tracer,
        "incident.major.declare",
        span_type=SpanType.REST_API,
        attributes={"incident.id": incident_id, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_assignment(tracer: Tracer, *, method: str, **attributes: object) -> Iterator[Span]:
    """Span one assignment decision."""
    with start_span(
        tracer,
        "incident.assignment.decide",
        span_type=SpanType.REST_API,
        attributes={"incident.assignment.method": method, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_report(tracer: Tracer, *, kind: str, rows: int, **attributes: object) -> Iterator[Span]:
    """Span a report build.

    Row count, never rows: a report body is exactly the incident detail
    somebody is entitled to see in one system and not in another.
    """
    with start_span(
        tracer,
        "incident.report.generate",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"incident.report_kind": kind, "incident.rows": rows, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "incident.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"incident.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_assignment",
    "trace_escalation",
    "trace_incident_create",
    "trace_incident_transition",
    "trace_major_incident_declare",
    "trace_publish",
    "trace_report",
    "trace_sla_sweep",
]
