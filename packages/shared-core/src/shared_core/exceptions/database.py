"""Database exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class DatabaseError(AIIOSException):
    """Raised when a database operation fails."""

    error_code = "AIIOS-DB-0001"
    status_code = 500
    severity = "high"
    retryable = True
    default_user_message = "A database error occurred. Please try again."
