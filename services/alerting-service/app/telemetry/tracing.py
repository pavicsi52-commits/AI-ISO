"""Alerting service telemetry.

Per docs/045 "TELEMETRY": Rule Evaluation, Correlation, Notification
Delivery, Escalation, Routing, Acknowledgements. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the paths a scheduled worker drives) with a
distinguishing span name, matching every prior AI-IOS service's
identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_rule_evaluation(tracer: Tracer, *, rule_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one rule's own evaluation against an incoming event ("Rule Evaluation")."""
    with start_span(
        tracer,
        "alerting.rule_evaluation",
        span_type=SpanType.BACKGROUND_JOB,
        rule_id=rule_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_correlation(tracer: Tracer, *, alert_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one alert's own correlation pass ("Correlation")."""
    with start_span(
        tracer,
        "alerting.correlation",
        span_type=SpanType.BACKGROUND_JOB,
        alert_id=alert_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_notification_delivery(
    tracer: Tracer, *, alert_id: str, channel: str, **attributes: object
) -> Iterator[Span]:
    """Trace one notification delivery attempt ("Notification Delivery")."""
    with start_span(
        tracer,
        "alerting.notification_delivery",
        span_type=SpanType.BACKGROUND_JOB,
        alert_id=alert_id,
        channel=channel,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_escalation(tracer: Tracer, *, alert_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one alert's own escalation decision ("Escalation")."""
    with start_span(
        tracer,
        "alerting.escalation",
        span_type=SpanType.BACKGROUND_JOB,
        alert_id=alert_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_routing(tracer: Tracer, *, alert_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one alert's own route selection ("Routing")."""
    with start_span(
        tracer,
        "alerting.routing",
        span_type=SpanType.REST_API,
        alert_id=alert_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_acknowledgement(tracer: Tracer, *, alert_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one acknowledgement being recorded ("Acknowledgements")."""
    with start_span(
        tracer,
        "alerting.acknowledgement",
        span_type=SpanType.REST_API,
        alert_id=alert_id,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_acknowledgement",
    "trace_correlation",
    "trace_escalation",
    "trace_notification_delivery",
    "trace_routing",
    "trace_rule_evaluation",
]
