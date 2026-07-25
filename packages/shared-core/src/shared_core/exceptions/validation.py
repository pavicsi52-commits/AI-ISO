"""Validation exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class ValidationError(AIIOSException):
    """Raised when input fails validation."""

    error_code = "AIIOS-VAL-0001"
    status_code = 400
    severity = "low"
    retryable = False
    default_user_message = "The request was invalid. Please check your input and try again."
