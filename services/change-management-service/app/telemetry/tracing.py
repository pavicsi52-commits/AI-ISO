"""Change management telemetry (docs/053 "TELEMETRY"): risk assessment,
approval flow, CAB processing, implementation, validation, rollback, and
reporting.

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for change-management work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Spans carry identifiers, levels, and counts, never change content.** A
title, description, or CAB agenda can describe a specific production
change in sensitive detail. It is stored deliberately and
access-controlled deliberately; a tracing backend has different
retention and different access rules, so putting any of it in a span
attribute would route that detail somewhere it was never meant to go --
and unlike a database row, a span cannot be redacted after the fact.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_change_create(
    tracer: Tracer, *, change_type: str, category: str, priority: str, **attributes: object
) -> Iterator[Span]:
    """Span opening one change request."""
    with start_span(
        tracer,
        "change.create",
        span_type=SpanType.REST_API,
        attributes={
            "change.type": change_type,
            "change.category": category,
            "change.priority": priority,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_change_transition(
    tracer: Tracer, *, from_status: str, to_status: str, **attributes: object
) -> Iterator[Span]:
    """Span a change lifecycle transition."""
    with start_span(
        tracer,
        "change.transition",
        span_type=SpanType.REST_API,
        attributes={
            "change.from_status": from_status,
            "change.to_status": to_status,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_risk_assessment(
    tracer: Tracer, *, risk_level: str, automated_score: float, **attributes: object
) -> Iterator[Span]:
    """Span computing one change's risk assessment."""
    with start_span(
        tracer,
        "change.risk.assess",
        span_type=SpanType.REST_API,
        attributes={
            "change.risk.level": risk_level,
            "change.risk.automated_score": automated_score,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_approval_decide(
    tracer: Tracer, *, level: int, decision: str, **attributes: object
) -> Iterator[Span]:
    """Span one approval step's decision.

    Level and decision are chain metadata, not who decided -- an
    approver's identity belongs in the approval row and the audit
    trail, not in a span attribute.
    """
    with start_span(
        tracer,
        "change.approval.decide",
        span_type=SpanType.REST_API,
        attributes={
            "change.approval.level": level,
            "change.approval.decision": decision,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_cab_close(
    tracer: Tracer, *, outcome: str | None, quorum_met: bool, votes: int, **attributes: object
) -> Iterator[Span]:
    """Span tallying and closing a CAB review."""
    with start_span(
        tracer,
        "change.cab.close",
        span_type=SpanType.REST_API,
        attributes={
            "change.cab.outcome": outcome or "none",
            "change.cab.quorum_met": quorum_met,
            "change.cab.votes": votes,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_implementation(tracer: Tracer, *, phase: str, **attributes: object) -> Iterator[Span]:
    """Span one implementation phase transition (start, validate, complete)."""
    with start_span(
        tracer,
        "change.implementation",
        span_type=SpanType.REST_API,
        attributes={"change.implementation.phase": phase, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_validation(
    tracer: Tracer, *, kind: str, status: str, is_gate: bool, **attributes: object
) -> Iterator[Span]:
    """Span one validation run."""
    with start_span(
        tracer,
        "change.validation.record",
        span_type=SpanType.REST_API,
        attributes={
            "change.validation.kind": kind,
            "change.validation.status": status,
            "change.validation.is_gate": is_gate,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_rollback(tracer: Tracer, *, phase: str, **attributes: object) -> Iterator[Span]:
    """Span one rollback phase transition (plan, start, complete, fail)."""
    with start_span(
        tracer,
        "change.rollback",
        span_type=SpanType.REST_API,
        attributes={"change.rollback.phase": phase, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_conflict_sweep(
    tracer: Tracer, *, changes_checked: int, conflicts_found: int, **attributes: object
) -> Iterator[Span]:
    """Span one conflict sweep tick."""
    with start_span(
        tracer,
        "change.conflict.sweep",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={
            "change.conflict.changes_checked": changes_checked,
            "change.conflict.conflicts_found": conflicts_found,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_report(tracer: Tracer, *, kind: str, rows: int, **attributes: object) -> Iterator[Span]:
    """Span a report build.

    Row count, never rows: a report body is exactly the change detail
    somebody is entitled to see in one system and not in another.
    """
    with start_span(
        tracer,
        "change.report.generate",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"change.report_kind": kind, "change.rows": rows, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "change.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        attributes={"change.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_approval_decide",
    "trace_cab_close",
    "trace_change_create",
    "trace_change_transition",
    "trace_conflict_sweep",
    "trace_implementation",
    "trace_publish",
    "trace_report",
    "trace_risk_assessment",
    "trace_rollback",
    "trace_validation",
]
