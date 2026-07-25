"""Rate limit exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class RateLimitError(AIIOSException):
    """Raised when a caller exceeds their allotted rate limit."""

    error_code = "AIIOS-RATE-0001"
    status_code = 429
    severity = "low"
    retryable = True
    default_user_message = "Too many requests. Please slow down and try again shortly."
