"""Authentication telemetry.

Per docs/030 "TELEMETRY": Trace Login, Logout, Session Creation, Token
Validation, Password Reset, MFA. "Integrate with Prompt 024." No
dedicated span type exists for authentication operations in
:class:`shared_core.telemetry.span.SpanType` (this is the first
microservice built on shared-core, not a shared framework prompt other
services extend), so every trace here uses the generic ``REST_API``
span type with an ``operation`` attribute distinguishing them --
matching :mod:`shared_core.plugins.telemetry`'s identical choice for
plugin load/hook/lifecycle tracing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_login(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one login attempt ("Login")."""
    with start_span(tracer, "auth.login", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_logout(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one logout ("Logout")."""
    with start_span(tracer, "auth.logout", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_session_creation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one session creation ("Session Creation")."""
    with start_span(
        tracer, "auth.session.create", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_token_validation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one token validation ("Token Validation")."""
    with start_span(
        tracer, "auth.token.validate", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_password_reset(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one password reset ("Password Reset")."""
    with start_span(
        tracer, "auth.password.reset", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_mfa(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one MFA operation ("MFA")."""
    with start_span(tracer, "auth.mfa", span_type=SpanType.REST_API, **attributes) as span:
        yield span


__all__ = [
    "trace_login",
    "trace_logout",
    "trace_mfa",
    "trace_password_reset",
    "trace_session_creation",
    "trace_token_validation",
]
