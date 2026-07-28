"""Monitoring service telemetry.

Per docs/044 "TELEMETRY": Collectors, Metric Processing, Aggregation,
Rule Evaluation, Time Series Storage, Dependency Resolution, Health
Calculation. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the collection/aggregation paths) with a
distinguishing ``operation`` attribute, matching every prior AI-IOS
service's identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_collectors(tracer: Tracer, *, collector_key: str, **attributes: object) -> Iterator[Span]:
    """Trace one collector's own data gathering against a target ("Collectors")."""
    with start_span(
        tracer,
        "monitoring.collectors",
        span_type=SpanType.BACKGROUND_JOB,
        collector_key=collector_key,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_metric_processing(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one collected value's own persistence into the time series ("Metric Processing")."""
    with start_span(
        tracer, "monitoring.metric_processing", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_aggregation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one time-series aggregation/downsampling pass ("Aggregation")."""
    with start_span(
        tracer, "monitoring.aggregation", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_rule_evaluation(tracer: Tracer, *, rule_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one rule's own evaluation against collected data ("Rule Evaluation")."""
    with start_span(
        tracer,
        "monitoring.rule_evaluation",
        span_type=SpanType.REST_API,
        rule_id=rule_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_time_series_storage(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one time-series data point's own write ("Time Series Storage")."""
    with start_span(
        tracer, "monitoring.time_series_storage", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_dependency_resolution(
    tracer: Tracer, *, target_id: str, **attributes: object
) -> Iterator[Span]:
    """Trace one target's own dependency graph walk ("Dependency Resolution")."""
    with start_span(
        tracer,
        "monitoring.dependency_resolution",
        span_type=SpanType.REST_API,
        target_id=target_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_health_calculation(
    tracer: Tracer, *, target_id: str, **attributes: object
) -> Iterator[Span]:
    """Trace one target's own overall health rollup ("Health Calculation")."""
    with start_span(
        tracer,
        "monitoring.health_calculation",
        span_type=SpanType.REST_API,
        target_id=target_id,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_aggregation",
    "trace_collectors",
    "trace_dependency_resolution",
    "trace_health_calculation",
    "trace_metric_processing",
    "trace_rule_evaluation",
    "trace_time_series_storage",
]
