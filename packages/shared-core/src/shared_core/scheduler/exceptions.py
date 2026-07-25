"""Scheduler-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.scheduler.SchedulerError`
so a bare ``except SchedulerError`` still catches everything raised
anywhere in this framework. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-025 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.scheduler``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-SCHEDULER-*`` range
against the base class's ``AIIOS-SCHEDULER-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.scheduler import SchedulerError


class InvalidScheduleError(SchedulerError):
    """Raised when a job's schedule (cron expression, calendar rule, ...) is invalid."""

    error_code = "AIIOS-SCHEDULER-0002"
    status_code = 422
    retryable = False
    default_user_message = "The job schedule is invalid."


class JobNotFoundError(SchedulerError):
    """Raised when a referenced job isn't registered."""

    error_code = "AIIOS-SCHEDULER-0003"
    status_code = 404
    retryable = False
    default_user_message = "The requested job does not exist."


class JobExecutionError(SchedulerError):
    """Raised when a job's payload raises during execution."""

    error_code = "AIIOS-SCHEDULER-0004"
    status_code = 500
    retryable = True
    default_user_message = "The job failed during execution."


class JobTimeoutError(SchedulerError):
    """Raised when a job exceeds its configured timeout."""

    error_code = "AIIOS-SCHEDULER-0005"
    status_code = 504
    retryable = True
    default_user_message = "The job exceeded its execution timeout."


class DependencyNotSatisfiedError(SchedulerError):
    """Raised when a job's dependencies aren't satisfied and it cannot run yet."""

    error_code = "AIIOS-SCHEDULER-0006"
    status_code = 409
    retryable = False
    default_user_message = "The job's dependencies are not yet satisfied."


class LeaderElectionError(SchedulerError):
    """Raised when leader election fails unexpectedly (not a normal "lost the race")."""

    error_code = "AIIOS-SCHEDULER-0007"
    status_code = 500
    retryable = True
    default_user_message = "Leader election failed."


class MaintenanceWindowActiveError(SchedulerError):
    """Raised when a job is rejected because a maintenance window is currently active."""

    error_code = "AIIOS-SCHEDULER-0008"
    status_code = 409
    retryable = True
    default_user_message = "Scheduling is currently suspended for a maintenance window."


__all__ = [
    "DependencyNotSatisfiedError",
    "InvalidScheduleError",
    "JobExecutionError",
    "JobNotFoundError",
    "JobTimeoutError",
    "LeaderElectionError",
    "MaintenanceWindowActiveError",
]
