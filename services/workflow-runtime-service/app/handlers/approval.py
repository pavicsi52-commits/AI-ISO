"""Builds the ``APPROVAL``/``HUMAN_TASK`` node handler.

Reads ``node.config``'s own ``approvers`` (list of approver identity
strings)/``required_approvals``/``timeout_seconds``, creates a
:class:`~app.models.workflow_approval.WorkflowApproval` row, and blocks
via :meth:`~app.services.approval.WorkflowApprovalService
.wait_for_decision` until a ``POST
/workflow-instances/{id}/approvals/{approval_id}/decide`` call resolves
it (or it times out). ``context.execution_id`` recovers this run's own
:class:`~app.models.workflow_instance.WorkflowInstance` id -- see
``app/services/execution.py``'s own docstring for why the two are set
equal by design.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    WorkflowContext,
)

from app.services.approval import WorkflowApprovalService


def build_approval_handler(
    approvals: WorkflowApprovalService, *, poll_interval_seconds: float
) -> NodeHandler:
    """Build the handler registered for both ``APPROVAL`` and ``HUMAN_TASK`` nodes."""

    async def handle_approval_node(
        node: NodeDefinition, context: WorkflowContext
    ) -> dict[str, str]:
        instance_id = UUID(context.execution_id)
        organization_id = UUID(context.organization_id) if context.organization_id else instance_id
        approval = await approvals.request(
            organization_id=organization_id,
            instance_id=instance_id,
            node_id=node.node_id,
            node_type=node.node_type,
            approvers=list(node.config.get("approvers", [])),
            required_approvals=int(node.config.get("required_approvals", 1)),
            timeout_seconds=float(node.config.get("timeout_seconds", node.timeout_seconds)),
        )
        decided = await approvals.wait_for_decision(
            approval.id, poll_interval_seconds=poll_interval_seconds
        )
        return {"approval_id": str(decided.id), "decision": str(decided.decision)}

    return handle_approval_node


def register_approval_handlers(
    registry: NodeHandlerRegistry,
    approvals: WorkflowApprovalService,
    *,
    poll_interval_seconds: float,
) -> None:
    """Register the same handler for both ``APPROVAL`` and ``HUMAN_TASK`` node types."""
    handler = build_approval_handler(approvals, poll_interval_seconds=poll_interval_seconds)
    registry.register(NodeType.APPROVAL, handler)
    registry.register(NodeType.HUMAN_TASK, handler)


__all__ = ["build_approval_handler", "register_approval_handlers"]
