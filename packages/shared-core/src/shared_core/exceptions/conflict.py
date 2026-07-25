"""Conflict exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class ConflictError(AIIOSException):
    """Raised when a request conflicts with existing state (e.g. duplicate,
    version mismatch)."""

    error_code = "AIIOS-CONFLICT-0001"
    status_code = 409
    severity = "low"
    retryable = False
    default_user_message = "This request conflicts with the current state of the resource."
