"""Telemetry-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.telemetry.TelemetryError`
so a bare ``except TelemetryError`` still catches everything raised
anywhere in this framework. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-023 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.telemetry``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-TELEMETRY-*`` range
against the base class's ``AIIOS-TELEMETRY-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.telemetry import TelemetryError


class SpanExportError(TelemetryError):
    """Raised when exporting one or more finished spans to a backend fails."""

    error_code = "AIIOS-TELEMETRY-0002"
    status_code = 500
    retryable = True
    default_user_message = "Telemetry data could not be exported."


class PropagationError(TelemetryError):
    """Raised when injecting or extracting trace context from a carrier fails."""

    error_code = "AIIOS-TELEMETRY-0003"
    status_code = 500
    retryable = False
    default_user_message = "Trace context could not be propagated."


class SamplingConfigurationError(TelemetryError):
    """Raised when a sampler is configured with invalid parameters."""

    error_code = "AIIOS-TELEMETRY-0004"
    status_code = 500
    retryable = False
    default_user_message = "The telemetry sampling configuration is invalid."


class SpanContextError(TelemetryError):
    """Raised when a span operation is attempted outside a valid trace context."""

    error_code = "AIIOS-TELEMETRY-0005"
    status_code = 500
    retryable = False
    default_user_message = "No active trace context is available."


class ExporterConfigurationError(TelemetryError):
    """Raised when a requested exporter cannot be configured (bad endpoint, unknown type)."""

    error_code = "AIIOS-TELEMETRY-0006"
    status_code = 500
    retryable = False
    default_user_message = "The telemetry exporter configuration is invalid."


__all__ = [
    "ExporterConfigurationError",
    "PropagationError",
    "SamplingConfigurationError",
    "SpanContextError",
    "SpanExportError",
]
