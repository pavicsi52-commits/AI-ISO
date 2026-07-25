"""Configuration exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class ConfigurationError(AIIOSException):
    """Raised when configuration is missing or invalid."""

    error_code = "AIIOS-CONFIG-0001"
    status_code = 500
    severity = "critical"
    retryable = False
    default_user_message = "The service is misconfigured. Please contact support."
