"""Human-in-the-loop approval (docs/060 "HUMAN-IN-THE-LOOP": Approval
Requests, Review Tasks, Clarification Requests, Pause Execution,
Resume Execution, Manual Overrides, Audit Trail).

Reuses ``shared_core.workflow.approval.ApprovalRequest``/
``ApprovalDecision`` directly rather than redefining an equivalent --
confirmed research finding: it "covers HUMAN-IN-THE-LOOP almost
verbatim" (Approve/Reject/Escalate/Delegate/Reminder/Expiration/Multi-
Level/Parallel Approval). "Review Tasks" and "Clarification Requests"
are the same gate under a different label, differentiated only by
``node.config['kind']`` and what "approve" means to the caller
(:mod:`app.langgraph.service`'s own ``ApprovalService.provide
_clarification`` treats a free-text answer as an approval that also
carries a workflow variable forward), never by a separate code path.

**Honest limit, confirmed by reading the engine's own source
(``shared_core/workflow/engine.py``)**: ``WorkflowEngine.run()`` always
starts a brand-new, empty ``WorkflowExecution`` and has no way to pre-
seed already-completed node results -- ``CheckpointStore.restore()``
exists but nothing in the engine's own ``run()`` calls it. There is no
sanctioned way to resume *only* from an ``APPROVAL`` node forward;
"Resume Execution" here means re-running the *whole* graph from
``START``, with the ``APPROVAL`` node itself the only node made
resume-safe (it checks for an already-resolved decision and passes
straight through rather than pausing again). Any node before an
approval gate that has side effects should be written idempotently --
the same caveat this SDK's own checkpoint module already carries for
crash recovery in general.

Since ``engine.run()`` never lets a node's own exception escape --
every node failure is caught and folded into
``execution.node_results[node_id].error`` as a plain string -- the
``APPROVAL`` node handler signals "paused, not failed" the only way
available: a recognisable message prefix
(:data:`AWAITING_APPROVAL_PREFIX`) that
:class:`~app.langgraph.service.WorkflowPersistenceService` checks for
after ``run()`` returns.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
)
from shared_core.workflow.approval import ApprovalDecision, ApprovalRequest

AWAITING_APPROVAL_PREFIX = "AWAITING_APPROVAL:"

ResolveApproval = Callable[[str], Awaitable[ApprovalRequest | None]]
"""Looks up a node's own pending (or resolved) request by id, or
``None`` if it was never requested."""

CreateApproval = Callable[[ApprovalRequest], Awaitable[None]]
"""Records a newly created request so a later lookup can find it."""


def approval_request_to_dict(request: ApprovalRequest) -> dict[str, Any]:
    """Serialise an :class:`ApprovalRequest` for storage in a JSON column."""
    return {
        "request_id": request.request_id,
        "node_id": request.node_id,
        "approvers": list(request.approvers),
        "required_approvals": request.required_approvals,
        "decision": str(request.decision),
        "decisions_by_approver": {
            approver: str(decision) for approver, decision in request.decisions_by_approver.items()
        },
        "delegated_to": request.delegated_to,
        "created_at": request.created_at.isoformat(),
        "timeout_seconds": request.timeout_seconds,
        "reminder_sent": request.reminder_sent,
    }


def approval_request_from_dict(data: dict[str, Any]) -> ApprovalRequest:
    """Deserialise a previously stored request."""
    return ApprovalRequest(
        request_id=data["request_id"],
        node_id=data["node_id"],
        approvers=tuple(data.get("approvers", ())),
        required_approvals=int(data.get("required_approvals", 1)),
        decision=ApprovalDecision(data.get("decision", str(ApprovalDecision.PENDING))),
        decisions_by_approver={
            approver: ApprovalDecision(decision)
            for approver, decision in (data.get("decisions_by_approver") or {}).items()
        },
        delegated_to=data.get("delegated_to"),
        created_at=datetime.fromisoformat(data["created_at"]),
        timeout_seconds=float(data.get("timeout_seconds", 3600.0)),
        reminder_sent=bool(data.get("reminder_sent", False)),
    )


def build_approval_node_handler(*, resolve: ResolveApproval, create: CreateApproval) -> NodeHandler:
    """Build the handler registered for ``APPROVAL`` nodes."""

    async def handle_approval_node(
        node: NodeDefinition, context: WorkflowContext
    ) -> dict[str, Any]:
        request_id = f"{context.execution_id}:{node.node_id}"
        existing = await resolve(request_id)

        if existing is not None:
            if existing.decision == ApprovalDecision.APPROVED:
                return {"decision": str(existing.decision), "request_id": request_id}
            if existing.decision in (ApprovalDecision.REJECTED, ApprovalDecision.EXPIRED):
                raise TaskExecutionError(
                    f"Approval node {node.node_id!r} was {existing.decision!s}: "
                    f"request {request_id!r}."
                )
            # Still PENDING/ESCALATED -- pause again rather than proceeding.
            raise TaskExecutionError(f"{AWAITING_APPROVAL_PREFIX}{request_id}")

        request = ApprovalRequest(
            request_id=request_id,
            node_id=node.node_id,
            approvers=tuple(node.config.get("approvers", ())),
            required_approvals=int(node.config.get("required_approvals", 1)),
            timeout_seconds=float(node.config.get("timeout_seconds", 3600.0)),
        )
        await create(request)
        raise TaskExecutionError(f"{AWAITING_APPROVAL_PREFIX}{request_id}")

    return handle_approval_node


def register_approval_node_handler(
    registry: NodeHandlerRegistry, *, resolve: ResolveApproval, create: CreateApproval
) -> None:
    """Register the ``APPROVAL`` node handler."""
    registry.register(
        NodeType.APPROVAL, build_approval_node_handler(resolve=resolve, create=create)
    )


__all__ = [
    "AWAITING_APPROVAL_PREFIX",
    "CreateApproval",
    "ResolveApproval",
    "approval_request_from_dict",
    "approval_request_to_dict",
    "build_approval_node_handler",
    "register_approval_node_handler",
]
