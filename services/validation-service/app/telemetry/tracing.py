"""Validation service telemetry.

Per docs/043 "TELEMETRY": Validation Engine, Rule Execution, Target
Collection, Result Aggregation, Scoring, Remediation Generation,
Execution Timing. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the engine/collection paths) with a
distinguishing ``operation`` attribute, matching every prior AI-IOS
service's identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_validation_engine(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one validation execution's own end-to-end run ("Validation Engine")."""
    with start_span(
        tracer,
        "validation.engine",
        span_type=SpanType.BACKGROUND_JOB,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_rule_execution(tracer: Tracer, *, check_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one rule chain's own evaluation against a check's own data ("Rule Execution")."""
    with start_span(
        tracer,
        "validation.rule_execution",
        span_type=SpanType.REST_API,
        check_id=check_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_target_collection(
    tracer: Tracer, *, collector_key: str, **attributes: object
) -> Iterator[Span]:
    """Trace one collector's own data gathering against a target ("Target Collection")."""
    with start_span(
        tracer,
        "validation.target_collection",
        span_type=SpanType.BACKGROUND_JOB,
        collector_key=collector_key,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_result_aggregation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one execution's own aggregate-status computation ("Result Aggregation")."""
    with start_span(
        tracer, "validation.result_aggregation", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_scoring(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one execution's own weighted scoring computation ("Scoring")."""
    with start_span(
        tracer, "validation.scoring", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_remediation_generation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one remediation suggestion's own generation ("Remediation Generation")."""
    with start_span(
        tracer, "validation.remediation_generation", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_execution_timing(
    tracer: Tracer, *, execution_id: str, **attributes: object
) -> Iterator[Span]:
    """Trace one execution's own overall wall-clock timing ("Execution Timing")."""
    with start_span(
        tracer,
        "validation.execution_timing",
        span_type=SpanType.BACKGROUND_JOB,
        execution_id=execution_id,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_execution_timing",
    "trace_remediation_generation",
    "trace_result_aggregation",
    "trace_rule_execution",
    "trace_scoring",
    "trace_target_collection",
    "trace_validation_engine",
]
