"""Cache exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class CacheError(AIIOSException):
    """Raised when a cache operation fails (Redis).

    Per docs/015 "RETRY POLICY": Redis failures are retryable -- cache is
    never the source of truth, so a retry (or falling through to the
    origin) is always safe.
    """

    error_code = "AIIOS-CACHE-0001"
    status_code = 503
    severity = "medium"
    retryable = True
    default_user_message = "A temporary error occurred. Please try again."
