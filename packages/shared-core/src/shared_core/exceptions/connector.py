"""Connector exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class ConnectorError(AIIOSException):
    """Raised when an infrastructure connector operation fails (connect,
    authenticate, execute, transfer, discover, or collect inventory).
    """

    error_code = "AIIOS-CONNECTOR-0001"
    status_code = 502
    severity = "medium"
    retryable = False
    default_user_message = "The connector operation could not be completed."
