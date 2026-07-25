"""Human approval.

Per docs/028_Enterprise_Workflow_SDK.md.txt "HUMAN APPROVAL": Approve,
Reject, Escalate, Delegate, Reminder, Expiration, Multi-Level Approval,
Parallel Approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from shared_core.workflow.constants import DEFAULT_APPROVAL_TIMEOUT_SECONDS
from shared_core.workflow.exceptions import ApprovalRejectedError, ApprovalTimeoutError


class ApprovalDecision(StrEnum):
    """Every decision an approval request can reach."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


@dataclass(slots=True)
class ApprovalRequest:
    """One human approval step's live state."""

    request_id: str
    node_id: str
    approvers: tuple[str, ...]
    required_approvals: int = 1
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decisions_by_approver: dict[str, ApprovalDecision] = field(default_factory=dict)
    delegated_to: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout_seconds: float = DEFAULT_APPROVAL_TIMEOUT_SECONDS
    reminder_sent: bool = False

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether this request has been pending past ``timeout_seconds`` ("Expiration")."""
        moment = now or datetime.now(UTC)
        return (
            self.decision == ApprovalDecision.PENDING
            and (moment - self.created_at).total_seconds() > self.timeout_seconds
        )

    def approve(self, approver: str) -> None:
        """Record *approver*'s approval ("Approve").

        Resolves once ``required_approvals`` is met ("Multi-Level
        Approval"/"Parallel Approval" -- multiple approvers may each
        call this independently, in any order).
        """
        self.decisions_by_approver[approver] = ApprovalDecision.APPROVED
        approvals = sum(
            1
            for decision in self.decisions_by_approver.values()
            if decision == ApprovalDecision.APPROVED
        )
        if approvals >= self.required_approvals:
            self.decision = ApprovalDecision.APPROVED

    def reject(self, approver: str) -> None:
        """Record *approver*'s rejection ("Reject") -- a single rejection resolves the request."""
        self.decisions_by_approver[approver] = ApprovalDecision.REJECTED
        self.decision = ApprovalDecision.REJECTED

    def escalate(self, *, to: str) -> None:
        """Escalate this request to *to* ("Escalate")."""
        self.decision = ApprovalDecision.ESCALATED
        self.delegated_to = to

    def delegate(self, *, to: str) -> None:
        """Delegate this request to *to*, still pending ("Delegate")."""
        self.delegated_to = to

    def mark_reminder_sent(self) -> None:
        """Record that a reminder was sent ("Reminder") -- avoids resending on every poll."""
        self.reminder_sent = True

    def resolve(self, *, now: datetime | None = None) -> ApprovalDecision:
        """Finalize this request's decision, expiring it if its timeout has passed.

        Raises:
            ApprovalTimeoutError: If the request expired without a decision.
            ApprovalRejectedError: If the request was rejected.
        """
        if self.is_expired(now=now):
            self.decision = ApprovalDecision.EXPIRED
            raise ApprovalTimeoutError(f"Approval request {self.request_id!r} expired.")
        if self.decision == ApprovalDecision.REJECTED:
            raise ApprovalRejectedError(f"Approval request {self.request_id!r} was rejected.")
        return self.decision


__all__ = ["ApprovalDecision", "ApprovalRequest"]
