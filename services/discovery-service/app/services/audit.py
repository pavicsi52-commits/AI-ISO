"""Discovery audit trail. Per docs/037 "AUDIT": Discovery Creation,
Execution, Cancellation, Profile Changes, Credential Usage, Inventory
Synchronization, Administrative Operations. **Zero plaintext/sensitive
persistence concern here** (like ``services/inventory-service``'s own
audit trail) -- "Credential Usage" records only which
:class:`~app.models.discovery_credential.DiscoveryCredential` (by id/
name) was used, never the resolved secret value itself.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.discovery_audit import DiscoveryAuditEntry
from app.models.enums import AuditOutcome
from app.repositories.discovery_audit import DiscoveryAuditRepository


class DiscoveryAuditService:
    """Records and lists privileged-action audit entries for a discovery job."""

    def __init__(self, audit: DiscoveryAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        job_id: UUID | None,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> DiscoveryAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            DiscoveryAuditEntry(
                job_id=job_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryAuditEntry]:
        """Every audit entry for *job_id*, newest first."""
        return await self._audit.list_for_job(job_id)


__all__ = ["DiscoveryAuditService"]
