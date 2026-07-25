"""Logging-framework exceptions.

Both subclass :class:`shared_core.exceptions.base.AIIOSException` directly
(there is no dedicated "logging" domain exception in the Prompt 012
baseline hierarchy) so they still flow through the standard error-handling
path everything else in AI-IOS uses.
"""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class LoggingConfigurationError(AIIOSException):
    """The logging framework was configured with an invalid setting."""

    error_code = "AIIOS-LOG-0001"
    status_code = 500
    severity = "high"
    retryable = False


class LogHandlerError(AIIOSException):
    """A log handler (file, OpenTelemetry, ...) failed to initialize or write."""

    error_code = "AIIOS-LOG-0002"
    status_code = 500
    severity = "high"
    retryable = False
