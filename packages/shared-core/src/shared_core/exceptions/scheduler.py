"""Scheduler exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class SchedulerError(AIIOSException):
    """Raised when scheduling, rescheduling, or dispatching a background
    job fails.
    """

    error_code = "AIIOS-SCHEDULER-0001"
    status_code = 500
    severity = "medium"
    retryable = False
    default_user_message = "The scheduled task could not be completed."
