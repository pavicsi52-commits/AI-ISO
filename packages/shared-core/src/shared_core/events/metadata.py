"""Event metadata and envelope helpers.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT FORMAT": every event
carries ``organization_id``/``project_id``/``user_id``/``correlation_id``/
``request_id`` alongside its own ``payload``/``metadata``. These helpers
auto-populate those framework-standard fields from the already-bound
request context (:mod:`shared_core.logging.context`,
:mod:`shared_core.security.context`) so publishing code doesn't have to
thread tenant/correlation IDs through by hand at every call site.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.logging.context import get_log_context
from shared_core.security.context import get_security_context


def default_correlation_id() -> str | None:
    """The current request's correlation ID, if any."""
    return get_log_context().correlation_id


def default_request_id() -> str | None:
    """The current request's request ID, if any."""
    return get_log_context().request_id


def default_organization_id() -> UUID | None:
    """The current request's organization ID, if any."""
    return get_security_context().organization_id


def default_project_id() -> UUID | None:
    """The current request's project ID, if any."""
    return get_security_context().project_id


def default_user_id() -> UUID | None:
    """The current request's authenticated user ID, if any."""
    return get_security_context().user_id


def build_metadata(**extra: Any) -> dict[str, Any]:
    """Build an event's ``metadata`` dict: trace context plus caller-supplied extras."""
    metadata: dict[str, Any] = {}
    context = get_log_context()
    if context.trace_id:
        metadata["trace_id"] = context.trace_id
    if context.span_id:
        metadata["span_id"] = context.span_id
    metadata.update(extra)
    return metadata


__all__ = [
    "build_metadata",
    "default_correlation_id",
    "default_organization_id",
    "default_project_id",
    "default_request_id",
    "default_user_id",
]
