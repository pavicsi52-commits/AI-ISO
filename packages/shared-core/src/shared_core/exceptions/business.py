"""Business rule exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class BusinessRuleError(AIIOSException):
    """Raised when a request violates a business rule (quota, approval
    required, maintenance window, etc.)."""

    error_code = "AIIOS-BIZ-0001"
    status_code = 422
    severity = "low"
    retryable = False
    default_user_message = "This request cannot be completed because it violates a business rule."
