"""Request-scoped logging context.

Populated by ``shared_core.middleware`` at the start of each request and
read by the JSON formatter so every log line carries the same correlation
fields, per docs/012_Shared_Core_Framework.md.txt "LOGGING" and
docs/014_Enterprise_Logging_Framework.md.txt "STRUCTURED CONTEXT".
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class LogContext:
    """Correlation fields attached to every structured log record."""

    request_id: str | None = None
    correlation_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


_context_var: ContextVar[LogContext | None] = ContextVar("log_context", default=None)


def get_log_context() -> LogContext:
    """Return the current request's log context."""
    return _context_var.get() or LogContext()


def bind_log_context(**fields: str | None) -> None:
    """Merge the given fields into the current log context."""
    _context_var.set(replace(get_log_context(), **fields))


def reset_log_context() -> None:
    """Clear the log context. Call at the end of each request."""
    _context_var.set(None)
