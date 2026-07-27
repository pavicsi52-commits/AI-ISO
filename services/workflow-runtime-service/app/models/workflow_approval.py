"""``workflow_approvals`` table -- one durable, DB-backed counterpart to
a ``shared_core.workflow.approval.ApprovalRequest``.

Per docs/042 "HUMAN APPROVALS" "Support": Approval Tasks, Multi-Level
Approval, Timeout, Escalation, Reassignment, Approval History,
Comments, Role-Based Approval. The SDK's own ``ApprovalRequest`` is a
plain in-memory dataclass with no engine integration at all (confirmed:
``APPROVAL``/``HUMAN_TASK`` are both delegated node types with no
built-in pause/resume mechanism) -- this table plus
``app/handlers/approval.py``'s poll-until-decided handler is what
actually blocks a running ``APPROVAL``/``HUMAN_TASK`` node until a
``POST`` decision arrives, mirroring ``ApprovalRequest``'s own field
shape so the two stay easy to reason about together.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.workflow import NodeType
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApprovalDecisionStatus


class WorkflowApproval(BaseModel):
    """One human-approval gate against a running workflow instance."""

    __tablename__ = "workflow_approvals"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), index=True)
    node_type: Mapped[NodeType] = mapped_column(String(32))
    approvers: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[ApprovalDecisionStatus] = mapped_column(
        String(16), default=ApprovalDecisionStatus.PENDING, index=True
    )
    decisions_by_approver: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    comments: Mapped[str | None] = mapped_column(Text, default=None)
    escalated_to: Mapped[str | None] = mapped_column(String(255), default=None)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=86400.0)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["WorkflowApproval"]
