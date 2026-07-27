"""Human-approval gates. Per docs/042 "HUMAN APPROVALS" "Support":
Approval Tasks, Multi-Level Approval, Timeout, Escalation,
Reassignment, Approval History, Comments, Role-Based Approval.

``shared_core.workflow.approval.ApprovalRequest`` has no engine
integration of its own (confirmed: ``APPROVAL``/``HUMAN_TASK`` are both
delegated node types with no built-in pause/resume mechanism) -- this
service is what actually blocks a running node until a decision
arrives, via :meth:`WorkflowApprovalService.wait_for_decision`'s
poll loop, called from ``app/handlers/approval.py``'s own
``NodeHandler``. Polling (not an in-memory ``asyncio.Event``) is a
deliberate, honest choice: it survives this process's own restarts as
long as the *waiting coroutine itself* stays alive, the same
"cooperative, not preemptive" limitation
``services/automation-service``'s own pause/cancel handling already
accepted, rather than pretending to support a decision arriving after
this specific worker process has died.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from shared_core.workflow import ApprovalRejectedError, ApprovalTimeoutError, NodeType

from app.models.enums import ApprovalDecisionStatus
from app.models.workflow_approval import WorkflowApproval
from app.repositories.workflow_approval import WorkflowApprovalRepository


class WorkflowApprovalService:
    """Requests, decides, and waits on human-approval gates."""

    def __init__(self, approvals: WorkflowApprovalRepository) -> None:
        self._approvals = approvals

    async def request(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        node_id: str,
        node_type: NodeType,
        approvers: list[str],
        required_approvals: int = 1,
        timeout_seconds: float = 86400.0,
    ) -> WorkflowApproval:
        """Request a new human-approval gate ("Approval Tasks")."""
        return await self._approvals.create(
            WorkflowApproval(
                organization_id=organization_id,
                instance_id=instance_id,
                node_id=node_id,
                node_type=node_type,
                approvers=approvers,
                required_approvals=required_approvals,
                timeout_seconds=timeout_seconds,
            )
        )

    async def get_by_id(self, approval_id: UUID) -> WorkflowApproval:
        """Return the approval gate identified by *approval_id*.

        Raises:
            NotFoundError: If no such approval gate exists.
        """
        return await self._approvals.require_by_id(approval_id)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowApproval]:
        """Every approval gate recorded for *instance_id* ("Approval History")."""
        return await self._approvals.list_for_instance(instance_id)

    async def list_pending_for_org(self, organization_id: UUID) -> list[WorkflowApproval]:
        """Every still-pending approval for *organization_id*."""
        return await self._approvals.list_pending_for_org(organization_id)

    async def decide(
        self, approval_id: UUID, *, approver: str, approve: bool, comments: str | None
    ) -> WorkflowApproval:
        """Record one approver's own decision ("Comments").

        A single rejection resolves the gate immediately
        (``REJECTED``); an approval only resolves it once
        ``required_approvals`` distinct approvers have approved
        ("Multi-Level Approval").

        Raises:
            NotFoundError: If no such approval gate exists.
        """
        approval = await self.get_by_id(approval_id)
        approval.decisions_by_approver[approver] = "approved" if approve else "rejected"
        approval.comments = comments
        if not approve:
            approval.decision = ApprovalDecisionStatus.REJECTED
            approval.decided_at = datetime.now(UTC)
        else:
            approved_count = sum(
                1 for decision in approval.decisions_by_approver.values() if decision == "approved"
            )
            if approved_count >= approval.required_approvals:
                approval.decision = ApprovalDecisionStatus.APPROVED
                approval.decided_at = datetime.now(UTC)
        return await self._approvals.update(approval)

    async def escalate(self, approval_id: UUID, *, escalate_to: str) -> WorkflowApproval:
        """Escalate a still-pending approval gate to another approver ("Escalation")."""
        approval = await self.get_by_id(approval_id)
        approval.escalated_to = escalate_to
        approval.decision = ApprovalDecisionStatus.ESCALATED
        return await self._approvals.update(approval)

    async def wait_for_decision(
        self, approval_id: UUID, *, poll_interval_seconds: float
    ) -> WorkflowApproval:
        """Poll *approval_id* until it is decided or expires.

        Raises:
            ApprovalRejectedError: If any approver rejects.
            ApprovalTimeoutError: If ``timeout_seconds`` elapses with no decision.
        """
        while True:
            approval = await self.get_by_id(approval_id)
            if approval.decision == ApprovalDecisionStatus.REJECTED:
                raise ApprovalRejectedError(f"Approval for node {approval.node_id!r} was rejected.")
            if approval.decision in (
                ApprovalDecisionStatus.APPROVED,
                ApprovalDecisionStatus.ESCALATED,
            ):
                return approval
            elapsed = (datetime.now(UTC) - approval.created_at).total_seconds()
            if elapsed >= approval.timeout_seconds:
                approval.decision = ApprovalDecisionStatus.EXPIRED
                await self._approvals.update(approval)
                raise ApprovalTimeoutError(
                    f"Approval for node {approval.node_id!r} timed out after "
                    f"{approval.timeout_seconds} seconds."
                )
            await asyncio.sleep(poll_interval_seconds)


__all__ = ["WorkflowApprovalService"]
