"""User management telemetry.

Per docs/031 "TELEMETRY": Profile Operations, Search, Import, Export,
Invitation, Avatar Upload. "Integrate with Prompt 024." Avatar
upload/download use :class:`shared_core.telemetry.span.SpanType`'s
``FILE_UPLOAD``/``FILE_DOWNLOAD`` members directly (they exist
specifically for this); import/export use ``BACKGROUND_JOB`` (they run
off the request/response cycle, per docs/031 "PERFORMANCE": "Background
Import"/"Background Export"); everything else (profile ops, search,
invitations) has no dedicated span type and falls back to ``REST_API``
with a distinguishing ``operation`` attribute, matching
``services/authentication-service``'s identical choice for the same
reason (this service didn't get its own ``SpanType`` member either).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_profile_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one profile read/write ("Profile Operations")."""
    with start_span(
        tracer, "user.profile", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_search(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one user-search request ("Search")."""
    with start_span(tracer, "user.search", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_import(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one background user-import job ("Import")."""
    with start_span(tracer, "user.import", span_type=SpanType.BACKGROUND_JOB, **attributes) as span:
        yield span


@contextmanager
def trace_export(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one background user-export job ("Export")."""
    with start_span(tracer, "user.export", span_type=SpanType.BACKGROUND_JOB, **attributes) as span:
        yield span


@contextmanager
def trace_invitation(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one invitation operation ("Invitation")."""
    with start_span(
        tracer, "user.invitation", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_avatar_upload(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one avatar upload ("Avatar Upload")."""
    with start_span(
        tracer, "user.avatar.upload", span_type=SpanType.FILE_UPLOAD, **attributes
    ) as span:
        yield span


__all__ = [
    "trace_avatar_upload",
    "trace_export",
    "trace_import",
    "trace_invitation",
    "trace_profile_operation",
    "trace_search",
]
