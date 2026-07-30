"""Policy engine telemetry (docs/050 "TELEMETRY").

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for policy work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Spans carry the shape of a decision, never its attributes.** A span
attribute is not an audit record, and the context a decision saw can hold
anything a caller sent -- including the credentials and personal
identifiers the decision log takes care to redact. Putting them in a
trace would route protected data into a system with different retention
and different access rules.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_evaluation(
    tracer: Tracer, *, resource_type: str, action: str, **attributes: object
) -> Iterator[Span]:
    """Trace one authorization decision.

    The subject is deliberately absent. Every protected operation on the
    platform produces one of these, so a span carrying who asked would
    turn the trace store into a per-user activity log -- a different
    system with different rules, and one this service already keeps
    properly in ``policy_decisions``.
    """
    with start_span(
        tracer,
        "policy.evaluate",
        span_type=SpanType.REST_API,
        resource_type=resource_type,
        action=action,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_rule_matching(
    tracer: Tracer, *, policy_slug: str, conditions: int, **attributes: object
) -> Iterator[Span]:
    """Trace one policy's rule evaluation."""
    with start_span(
        tracer,
        "policy.rule_match",
        span_type=SpanType.REST_API,
        policy_slug=policy_slug,
        conditions=conditions,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_decision_generation(
    tracer: Tracer, *, effect: str, matched: int, **attributes: object
) -> Iterator[Span]:
    """Trace combining many matched policies into one effect."""
    with start_span(
        tracer,
        "policy.decide",
        span_type=SpanType.REST_API,
        effect=effect,
        matched=matched,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_simulation(
    tracer: Tracer, *, label: str, requests: int, **attributes: object
) -> Iterator[Span]:
    """Trace one policy simulation."""
    with start_span(
        tracer,
        "policy.simulate",
        span_type=SpanType.BACKGROUND_JOB,
        label=label,
        requests=requests,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_approval(tracer: Tracer, *, approval_type: str, **attributes: object) -> Iterator[Span]:
    """Trace one approval obligation being raised or resolved."""
    with start_span(
        tracer,
        "policy.approval",
        span_type=SpanType.BACKGROUND_JOB,
        approval_type=approval_type,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_quota_evaluation(
    tracer: Tracer, *, resource: str, **attributes: object
) -> Iterator[Span]:
    """Trace one quota check."""
    with start_span(
        tracer,
        "policy.quota",
        span_type=SpanType.REST_API,
        resource=resource,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_publish(
    tracer: Tracer, *, policy_slug: str, version: str, **attributes: object
) -> Iterator[Span]:
    """Trace one policy being compiled and published."""
    with start_span(
        tracer,
        "policy.publish",
        span_type=SpanType.BACKGROUND_JOB,
        policy_slug=policy_slug,
        version=version,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_approval",
    "trace_decision_generation",
    "trace_evaluation",
    "trace_publish",
    "trace_quota_evaluation",
    "trace_rule_matching",
    "trace_simulation",
]
