"""``workflow_audit`` table. Per docs/042 "AUDIT": Workflow Execution,
State Changes, Approvals, Replay, Rollback, Checkpoint, Administrative
Operations. Class named ``WorkflowAuditEntry``, not ``WorkflowAudit``,
matching the same "avoid a bare-noun class name that reads like a
verb/table-name collision" precedent
``services/playbook-service``'s own ``PlaybookAuditEntry`` established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class WorkflowAuditEntry(BaseModel):
    """One privileged/administrative action recorded against a workflow."""

    __tablename__ = "workflow_audit"

    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="SET NULL"), default=None, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["WorkflowAuditEntry"]
