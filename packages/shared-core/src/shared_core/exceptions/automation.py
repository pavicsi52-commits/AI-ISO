"""Automation subsystem exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class AutomationError(AIIOSException):
    """Raised when a playbook or workflow execution fails."""

    error_code = "AIIOS-AUTO-0001"
    status_code = 500
    severity = "high"
    retryable = False
    default_user_message = "The automation could not be completed. Please try again."
