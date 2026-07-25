"""Timeout exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class AIIOSTimeoutError(AIIOSException):
    """Raised when an operation exceeds its allotted time.

    Named ``AIIOSTimeoutError`` (not ``TimeoutError``) to avoid shadowing
    the Python builtin.
    """

    error_code = "AIIOS-TIMEOUT-0001"
    status_code = 504
    severity = "medium"
    retryable = True
    default_user_message = "The request took too long to complete. Please try again."
