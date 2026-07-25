"""Network exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class NetworkError(AIIOSException):
    """Raised when a network-level operation fails (connection refused,
    DNS failure, transient socket error). Per docs/015 "RETRY POLICY":
    temporary network failures are retryable.
    """

    error_code = "AIIOS-NETWORK-0001"
    status_code = 503
    severity = "high"
    retryable = True
    default_user_message = "A network error occurred. Please try again."
