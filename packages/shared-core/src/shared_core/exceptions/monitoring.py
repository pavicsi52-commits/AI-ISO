"""Monitoring subsystem exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class MonitoringError(AIIOSException):
    """Raised when the monitoring subsystem itself fails (metric export,
    health-check aggregation) -- not for the conditions monitoring detects.
    """

    error_code = "AIIOS-MONITORING-0001"
    status_code = 500
    severity = "medium"
    retryable = False
    default_user_message = "A monitoring error occurred."
