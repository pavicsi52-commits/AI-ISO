"""Workflow-SDK-specific exceptions.

Each subclasses :class:`shared_core.exceptions.workflow.WorkflowError`
(pre-seeded in Prompt 012's baseline skeleton, unlike Prompt 027's
``ConnectorError`` which had to be added fresh) so a bare ``except
WorkflowError`` still catches everything raised anywhere in this SDK.
Not registered in :mod:`shared_core.exceptions.constants`'s central
catalog -- same reasoning as every other Prompt 018-027 framework: that
module would need to import from here, and this module already imports
from ``shared_core.exceptions.workflow``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-WORKFLOW-*`` range
against the base class's ``AIIOS-WORKFLOW-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.workflow import WorkflowError


class InvalidWorkflowDefinitionError(WorkflowError):
    """Raised when a workflow definition fails parsing or validation."""

    error_code = "AIIOS-WORKFLOW-0002"
    status_code = 422
    retryable = False
    default_user_message = "The workflow definition is invalid."


class WorkflowNotFoundError(WorkflowError):
    """Raised when a referenced workflow definition isn't registered."""

    error_code = "AIIOS-WORKFLOW-0003"
    status_code = 404
    retryable = False
    default_user_message = "The requested workflow does not exist."


class CycleDetectedError(WorkflowError):
    """Raised when a workflow's node graph contains a cycle (not a valid DAG)."""

    error_code = "AIIOS-WORKFLOW-0004"
    status_code = 422
    retryable = False
    default_user_message = "The workflow definition contains a cycle."


class NodeNotFoundError(WorkflowError):
    """Raised when a referenced node id isn't present in the workflow's graph."""

    error_code = "AIIOS-WORKFLOW-0005"
    status_code = 404
    retryable = False
    default_user_message = "The referenced workflow node does not exist."


class TaskExecutionError(WorkflowError):
    """Raised when a node's task execution raises."""

    error_code = "AIIOS-WORKFLOW-0006"
    status_code = 500
    retryable = True
    default_user_message = "A workflow task failed during execution."


class WorkflowTimeoutError(WorkflowError):
    """Raised when a workflow or task exceeds its configured timeout."""

    error_code = "AIIOS-WORKFLOW-0007"
    status_code = 504
    retryable = True
    default_user_message = "The workflow exceeded its execution timeout."


class InvalidStateTransitionError(WorkflowError):
    """Raised when a state machine transition isn't allowed from the current state."""

    error_code = "AIIOS-WORKFLOW-0008"
    status_code = 409
    retryable = False
    default_user_message = "That workflow state transition is not allowed."


class CheckpointError(WorkflowError):
    """Raised when saving or restoring a workflow checkpoint fails."""

    error_code = "AIIOS-WORKFLOW-0009"
    status_code = 500
    retryable = True
    default_user_message = "The workflow checkpoint could not be saved or restored."


class RollbackError(WorkflowError):
    """Raised when rolling back a workflow's executed steps fails."""

    error_code = "AIIOS-WORKFLOW-0010"
    status_code = 500
    retryable = False
    default_user_message = "The workflow rollback could not be completed."


class CompensationError(WorkflowError):
    """Raised when a registered compensation action fails."""

    error_code = "AIIOS-WORKFLOW-0011"
    status_code = 500
    retryable = False
    default_user_message = "A workflow compensation action failed."


class ApprovalTimeoutError(WorkflowError):
    """Raised when a human approval step isn't decided within its timeout."""

    error_code = "AIIOS-WORKFLOW-0012"
    status_code = 504
    retryable = False
    default_user_message = "The approval request expired without a decision."


class ApprovalRejectedError(WorkflowError):
    """Raised when a human approval step is rejected."""

    error_code = "AIIOS-WORKFLOW-0013"
    status_code = 409
    retryable = False
    default_user_message = "The approval request was rejected."


class ExpressionEvaluationError(WorkflowError):
    """Raised when a condition/variable expression fails to evaluate."""

    error_code = "AIIOS-WORKFLOW-0014"
    status_code = 422
    retryable = False
    default_user_message = "A workflow expression could not be evaluated."


class MaxIterationsExceededError(WorkflowError):
    """Raised when a loop node exceeds its configured maximum iteration count."""

    error_code = "AIIOS-WORKFLOW-0015"
    status_code = 500
    retryable = False
    default_user_message = "The workflow loop exceeded its maximum iteration count."


__all__ = [
    "ApprovalRejectedError",
    "ApprovalTimeoutError",
    "CheckpointError",
    "CompensationError",
    "CycleDetectedError",
    "ExpressionEvaluationError",
    "InvalidStateTransitionError",
    "InvalidWorkflowDefinitionError",
    "MaxIterationsExceededError",
    "NodeNotFoundError",
    "RollbackError",
    "TaskExecutionError",
    "WorkflowNotFoundError",
    "WorkflowTimeoutError",
]
