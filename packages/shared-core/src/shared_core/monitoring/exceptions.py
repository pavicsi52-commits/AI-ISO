"""Monitoring-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.monitoring.MonitoringError`
so a bare ``except MonitoringError`` still catches everything raised
anywhere in this framework. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-021 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.monitoring``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-MONITORING-*`` range
against the base class's ``AIIOS-MONITORING-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.monitoring import MonitoringError


class HealthCheckFailedError(MonitoringError):
    """Raised when a registered health check itself errors (not merely reports unhealthy)."""

    error_code = "AIIOS-MONITORING-0002"
    status_code = 500
    retryable = True
    default_user_message = "A health check could not be completed."


class DependencyUnavailableError(MonitoringError):
    """Raised when a monitored dependency is unreachable during a deep health check."""

    error_code = "AIIOS-MONITORING-0003"
    status_code = 503
    retryable = True
    default_user_message = "A required dependency is currently unavailable."


class ThresholdEvaluationError(MonitoringError):
    """Raised when evaluating a metric against its configured thresholds fails."""

    error_code = "AIIOS-MONITORING-0004"
    status_code = 500
    retryable = False
    default_user_message = "The threshold could not be evaluated."


class AlertDispatchError(MonitoringError):
    """Raised when an alert fails to reach its registered sink(s)."""

    error_code = "AIIOS-MONITORING-0005"
    status_code = 500
    retryable = True
    default_user_message = "The alert could not be dispatched."


class RegistrationError(MonitoringError):
    """Raised when registering a check, metric, threshold, or dashboard with the registry fails."""

    error_code = "AIIOS-MONITORING-0006"
    status_code = 500
    retryable = False
    default_user_message = "The monitoring registration could not be completed."


__all__ = [
    "AlertDispatchError",
    "DependencyUnavailableError",
    "HealthCheckFailedError",
    "RegistrationError",
    "ThresholdEvaluationError",
]
