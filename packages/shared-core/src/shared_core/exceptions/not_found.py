"""Not-found exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class NotFoundError(AIIOSException):
    """Raised when a requested resource does not exist."""

    error_code = "AIIOS-NF-0001"
    status_code = 404
    severity = "low"
    retryable = False
    default_user_message = "The requested resource was not found."
