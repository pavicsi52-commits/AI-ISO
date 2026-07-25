"""Database Query span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": Database
Query. Instruments :mod:`shared_core.database` operations without that
package depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_database_query(
    tracer: Tracer, operation: str, *, table: str | None = None, **attributes: str
) -> Iterator[Span]:
    """Trace one database query ("Database Query"; "PERFORMANCE PROFILING": Database Queries)."""
    name = f"database.query {operation}" if table is None else f"database.query {operation} {table}"
    if table is not None:
        attributes["db.table"] = table
    with start_span(tracer, name, span_type=SpanType.DATABASE_QUERY, **attributes) as span:
        yield span


__all__ = ["trace_database_query"]
