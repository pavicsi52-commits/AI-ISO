"""Authentication exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class AuthenticationError(AIIOSException):
    """Raised when a request cannot be authenticated."""

    error_code = "AIIOS-AUTH-0001"
    status_code = 401
    severity = "medium"
    retryable = False
    default_user_message = "Authentication failed. Please sign in again."
