"""Workflow audit trail.

Per docs/028_Enterprise_Workflow_SDK.md.txt "AUDIT": Workflow Created,
Workflow Updated, Workflow Deleted, Execution Started, Execution
Completed, Execution Failed, Rollback Executed, Approval Decision.
Also "SECURITY": Audit Privileged Workflows. Emitted as structured log
events via :meth:`shared_core.logging.logger.AIIOSLogger.audit`
(Prompt 014) rather than persisted to a database table -- same
reasoning as every other Prompt 018-027 framework's own audit.py.
"""

from __future__ import annotations

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.workflow.audit")


def audit_workflow_created(workflow_id: str, *, actor_id: str | None = None) -> None:
    """Record that a workflow definition was created ("Workflow Created")."""
    logger.audit("workflow.create", actor_id=actor_id, resource=workflow_id)


def audit_workflow_updated(workflow_id: str, *, actor_id: str | None = None) -> None:
    """Record that a workflow definition was updated ("Workflow Updated")."""
    logger.audit("workflow.update", actor_id=actor_id, resource=workflow_id)


def audit_workflow_deleted(workflow_id: str, *, actor_id: str | None = None) -> None:
    """Record that a workflow definition was deleted ("Workflow Deleted")."""
    logger.audit("workflow.delete", actor_id=actor_id, resource=workflow_id)


def audit_execution_started(
    execution_id: str, workflow_id: str, *, actor_id: str | None = None
) -> None:
    """Record that a workflow execution started ("Execution Started")."""
    logger.audit(
        "workflow.execution.start",
        actor_id=actor_id,
        resource=execution_id,
        workflow_id=workflow_id,
    )


def audit_execution_completed(
    execution_id: str, workflow_id: str, *, actor_id: str | None = None
) -> None:
    """Record that a workflow execution completed ("Execution Completed")."""
    logger.audit(
        "workflow.execution.complete",
        actor_id=actor_id,
        resource=execution_id,
        workflow_id=workflow_id,
    )


def audit_execution_failed(
    execution_id: str, workflow_id: str, *, error: str, actor_id: str | None = None
) -> None:
    """Record that a workflow execution failed ("Execution Failed")."""
    logger.audit(
        "workflow.execution.fail",
        actor_id=actor_id,
        resource=execution_id,
        workflow_id=workflow_id,
        error=error,
    )


def audit_rollback_executed(
    execution_id: str, workflow_id: str, *, node_ids: list[str], actor_id: str | None = None
) -> None:
    """Record that a rollback executed ("Rollback Executed")."""
    logger.audit(
        "workflow.rollback",
        actor_id=actor_id,
        resource=execution_id,
        workflow_id=workflow_id,
        node_ids=node_ids,
    )


def audit_approval_decision(request_id: str, node_id: str, *, decision: str, approver: str) -> None:
    """Record an approval decision ("Approval Decision")."""
    logger.audit(
        "workflow.approval.decision",
        actor_id=approver,
        resource=request_id,
        node_id=node_id,
        decision=decision,
    )


def audit_privileged_access(
    execution_id: str, workflow_id: str, *, operation: str, actor_id: str | None = None
) -> None:
    """Record access to a privileged workflow operation ("Audit Privileged Workflows")."""
    logger.audit(
        "workflow.privileged.access",
        actor_id=actor_id,
        resource=execution_id,
        workflow_id=workflow_id,
        operation=operation,
    )


__all__ = [
    "audit_approval_decision",
    "audit_execution_completed",
    "audit_execution_failed",
    "audit_execution_started",
    "audit_privileged_access",
    "audit_rollback_executed",
    "audit_workflow_created",
    "audit_workflow_deleted",
    "audit_workflow_updated",
]
