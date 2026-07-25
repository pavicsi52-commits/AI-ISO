"""Request-scoped HTTP context for log records.

Distinct from :mod:`shared_core.logging.context`, which carries
identity/correlation fields relevant to *every* log record (HTTP or not).
This module carries the HTTP-specific fields from
docs/014_Enterprise_Logging_Framework.md.txt "LOG FORMAT" (``method``,
``url``, ``ip_address``, ``user_agent``) that only apply while handling a
request, populated by :class:`shared_core.logging.middleware.RequestLoggingMiddleware`.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class RequestLogContext:
    """HTTP request fields attached to log records emitted while handling it."""

    method: str | None = None
    url: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


_context_var: ContextVar[RequestLogContext | None] = ContextVar("request_log_context", default=None)


def get_request_log_context() -> RequestLogContext:
    """Return the current request's HTTP log context."""
    return _context_var.get() or RequestLogContext()


def bind_request_log_context(**fields: str | None) -> None:
    """Merge the given fields into the current request log context."""
    _context_var.set(replace(get_request_log_context(), **fields))


def reset_request_log_context() -> None:
    """Clear the request log context. Call at the end of each request."""
    _context_var.set(None)
