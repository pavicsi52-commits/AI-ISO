"""Authorization exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class AuthorizationError(AIIOSException):
    """Raised when an authenticated caller lacks permission."""

    error_code = "AIIOS-AUTHZ-0001"
    status_code = 403
    severity = "medium"
    retryable = False
    default_user_message = "You do not have permission to perform this action."
