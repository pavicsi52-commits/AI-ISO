"""Automation service audit trail.

Per docs/040 "AUDIT": Automation Creation, Execution, Cancellation,
Approval, Rollback, Configuration Changes, Target Selection,
Administrative Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.automation_audit import AutomationAuditEntry
from app.models.enums import AuditOutcome
from app.repositories.automation_audit import AutomationAuditRepository


class AutomationAuditService:
    """Records and lists privileged-action audit entries for jobs and executions."""

    def __init__(self, audit: AutomationAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        *,
        job_id: UUID | None,
        execution_id: UUID | None,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AutomationAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            AutomationAuditEntry(
                job_id=job_id,
                execution_id=execution_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[AutomationAuditEntry]:
        """Every audit entry for *job_id*, newest first."""
        return await self._audit.list_for_job(job_id)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationAuditEntry]:
        """Every audit entry for *execution_id*, newest first."""
        return await self._audit.list_for_execution(execution_id)


__all__ = ["AutomationAuditService"]
