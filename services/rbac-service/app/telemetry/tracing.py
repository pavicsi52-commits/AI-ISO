"""RBAC service telemetry.

Per docs/032 "TELEMETRY": Authorization Evaluation, Policy Evaluation,
Permission Lookup, Role Assignment, Permission Cache. "Integrate
Prompt 024." Permission Cache uses
:class:`shared_core.telemetry.span.SpanType`'s ``CACHE_ACCESS`` member
directly (it exists specifically for this); everything else has no
dedicated span type and falls back to ``REST_API`` with a
distinguishing ``operation``/attribute set, matching
``services/user-management-service``'s identical choice for the same
reason (this service didn't get its own ``SpanType`` member either).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_authorization_evaluation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one ``POST /authorization/evaluate`` call ("Authorization Evaluation")."""
    with start_span(
        tracer, "rbac.authorization.evaluate", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_policy_evaluation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one policy's condition evaluation ("Policy Evaluation")."""
    with start_span(
        tracer, "rbac.policy.evaluate", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_permission_lookup(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one effective-permission resolution ("Permission Lookup")."""
    with start_span(
        tracer, "rbac.permission.lookup", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_role_assignment(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one role-assignment mutation ("Role Assignment")."""
    with start_span(
        tracer,
        "rbac.role.assignment",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_permission_cache(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one permission-cache read/write ("Permission Cache")."""
    with start_span(
        tracer,
        "rbac.permission_cache",
        span_type=SpanType.CACHE_ACCESS,
        operation=operation,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_authorization_evaluation",
    "trace_permission_cache",
    "trace_permission_lookup",
    "trace_policy_evaluation",
    "trace_role_assignment",
]
