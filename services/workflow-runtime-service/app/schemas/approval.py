"""Request/response schemas for workflow human-approval gates.

``POST /workflow-instances/{instance_id}/approvals/{approval_id}/decide``
is not itself in docs/042's own literal REST APIs list (17 endpoints,
all under ``/workflows``/``/workflow-instances``/``/workflow``) --
added directly, the same "a required capability with no REST list
entry of its own still needs a real, reachable endpoint" precedent
``services/configuration-management-service``'s own baselines/
variables/policies endpoints already established, since without it
"Human Approvals" (an explicit ACCEPTANCE CRITERIA line) would have no
way to ever actually be decided.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.workflow import NodeType

from app.models.enums import ApprovalDecisionStatus


class WorkflowApprovalDecisionRequest(BaseModel):
    """Body of the approval-decision action."""

    approver: str = Field(min_length=1, max_length=255)
    approve: bool
    comments: str | None = Field(default=None, max_length=4096)


class WorkflowApprovalResponse(BaseModel):
    """One human-approval gate against a running workflow instance."""

    id: UUID
    instance_id: UUID
    node_id: str
    node_type: NodeType
    approvers: list[str]
    required_approvals: int
    decision: ApprovalDecisionStatus
    decisions_by_approver: dict[str, str]
    comments: str | None
    escalated_to: str | None
    timeout_seconds: float
    decided_at: datetime | None


__all__ = ["WorkflowApprovalDecisionRequest", "WorkflowApprovalResponse"]
