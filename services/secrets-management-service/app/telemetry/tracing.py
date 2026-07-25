"""Secrets management service telemetry.

Per docs/035 "TELEMETRY": Secret Access, Encryption, Decryption,
Rotation, Lease Operations, Certificate Validation, Provider Calls.
"Integrate Prompt 024." No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or ``BACKGROUND_JOB``
for the scheduled-worker paths) with a distinguishing ``operation``
attribute, matching every prior AI-IOS service's identical choice for
the same reason. **No span attribute here ever carries a secret's
plaintext or ciphertext value** -- only ids, names, and outcomes -- per
docs/035's own "Never log plaintext secrets".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_secret_access(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one secret access ("Secret Access": create/read/update/delete)."""
    with start_span(
        tracer, "secret.access", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_encryption(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one encryption operation ("Encryption")."""
    with start_span(tracer, "secret.encrypt", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_decryption(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one decryption operation ("Decryption")."""
    with start_span(tracer, "secret.decrypt", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_rotation(tracer: Tracer, *, trigger: str, **attributes: object) -> Iterator[Span]:
    """Trace one rotation attempt ("Rotation")."""
    with start_span(
        tracer, "secret.rotation", span_type=SpanType.BACKGROUND_JOB, trigger=trigger, **attributes
    ) as span:
        yield span


@contextmanager
def trace_lease_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one lease operation ("Lease Operations": issue/renew/revoke)."""
    with start_span(
        tracer, "secret.lease", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_certificate_validation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one certificate validation ("Certificate Validation")."""
    with start_span(
        tracer, "secret.certificate_validation", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_provider_call(
    tracer: Tracer, *, provider_type: str, **attributes: object
) -> Iterator[Span]:
    """Trace one external provider call ("Provider Calls")."""
    with start_span(
        tracer,
        "secret.provider_call",
        span_type=SpanType.REST_API,
        provider_type=provider_type,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_certificate_validation",
    "trace_decryption",
    "trace_encryption",
    "trace_lease_operation",
    "trace_provider_call",
    "trace_rotation",
    "trace_secret_access",
]
