"""Generic service-level exceptions.

The three "EXCEPTION CATEGORIES" from docs/015_Enterprise_Exception_Framework.md.txt
that have no dedicated domain of their own: ``Internal`` (a bug in this
service), ``External`` (a downstream third-party service failed), and
``Unknown`` (an exception :mod:`shared_core.exceptions.mapper` couldn't
classify at all -- the catch-all of last resort).
"""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class InternalError(AIIOSException):
    """Raised for an unexpected internal failure -- a bug, not a caller error."""

    error_code = "AIIOS-INTERNAL-0001"
    status_code = 500
    severity = "critical"
    retryable = False
    default_user_message = "An internal error occurred. Please contact support."


class ExternalError(AIIOSException):
    """Raised when a downstream third-party service (outside AI-IOS) fails."""

    error_code = "AIIOS-EXTERNAL-0001"
    status_code = 502
    severity = "high"
    retryable = True
    default_user_message = "An external service is temporarily unavailable. Please try again."


class UnknownError(AIIOSException):
    """The catch-all for an exception that couldn't be classified into any
    other category. Should be rare in practice -- every occurrence is a
    signal that :mod:`shared_core.exceptions.mapper` is missing a mapping.
    """

    error_code = "AIIOS-UNKNOWN-0001"
    status_code = 500
    severity = "critical"
    retryable = False
    default_user_message = "An unexpected error occurred. Please contact support."
