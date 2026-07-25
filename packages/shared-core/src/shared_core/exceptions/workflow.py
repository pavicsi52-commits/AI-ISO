"""Workflow exception."""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class WorkflowError(AIIOSException):
    """Raised when a workflow's execution fails or reaches an invalid state."""

    error_code = "AIIOS-WORKFLOW-0001"
    status_code = 500
    severity = "high"
    retryable = False
    default_user_message = "The workflow could not be completed. Please try again."
