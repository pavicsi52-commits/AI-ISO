"""Audit trail. Per docs/042 "AUDIT": Workflow Execution, State Changes,
Approvals, Replay, Rollback, Checkpoint, Administrative Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.workflow_audit import WorkflowAuditEntry
from app.repositories.workflow_audit import WorkflowAuditEntryRepository


class WorkflowAuditService:
    """Records and reads privileged/administrative actions."""

    def __init__(self, audit: WorkflowAuditEntryRepository) -> None:
        self._audit = audit

    async def record(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID | None,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> WorkflowAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            WorkflowAuditEntry(
                organization_id=organization_id,
                instance_id=instance_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowAuditEntry]:
        """Every audit entry recorded against *instance_id*."""
        return await self._audit.list_for_instance(instance_id)


__all__ = ["WorkflowAuditService"]
