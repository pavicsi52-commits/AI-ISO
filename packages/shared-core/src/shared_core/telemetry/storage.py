"""File Upload/Download span helpers.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": File
Upload, File Download. Instruments :mod:`shared_core.storage` operations
without that package depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_file_upload(tracer: Tracer, object_name: str, **attributes: str) -> Iterator[Span]:
    """Trace one file upload ("File Upload"; "PERFORMANCE PROFILING": Storage Operations)."""
    with start_span(
        tracer,
        f"storage.upload {object_name}",
        span_type=SpanType.FILE_UPLOAD,
        object_name=object_name,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_file_download(tracer: Tracer, object_name: str, **attributes: str) -> Iterator[Span]:
    """Trace one file download ("File Download"; "PERFORMANCE PROFILING": Storage Operations)."""
    with start_span(
        tracer,
        f"storage.download {object_name}",
        span_type=SpanType.FILE_DOWNLOAD,
        object_name=object_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_file_download", "trace_file_upload"]
