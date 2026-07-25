"""Telemetry subsystem exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class TelemetryError(AIIOSException):
    """Raised when the telemetry subsystem itself fails (span export,
    trace-context propagation) -- not for conditions telemetry observes
    in the traced operation itself.
    """

    error_code = "AIIOS-TELEMETRY-0001"
    status_code = 500
    severity = "medium"
    retryable = False
    default_user_message = "A telemetry error occurred."
