"""Dependency exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class DependencyError(AIIOSException):
    """Raised when a required external dependency (database, cache, queue,
    downstream service) is unavailable."""

    error_code = "AIIOS-DEP-0001"
    status_code = 503
    severity = "high"
    retryable = True
    default_user_message = (
        "A required service is temporarily unavailable. Please try again shortly."
    )
