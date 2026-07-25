"""Organization audit trail.

Per docs/033 "AUDIT": Organization Creation, Updates, Deletion,
Settings Changes, Branding Changes, License Changes, Quota Changes,
Member Invitations, Administrative Actions. Routine column-level
Create/Update/Delete auditing for every table is already automatic via
:mod:`shared_core.database.audit`, wired into ``BaseRepository`` itself
-- this records specifically *privileged* actions with a before/after
snapshot, the same distinction ``app/models/audit.py``'s docstring
draws from ``app/services/activity.py``'s narrative feed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.audit import OrganizationAuditEntry
from app.models.enums import AuditOutcome
from app.repositories.audit import OrganizationAuditRepository


class OrganizationAuditService:
    """Records and lists privileged-action audit entries for an organization."""

    def __init__(self, audit: OrganizationAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        organization_id: UUID,
        *,
        actor_id: UUID | None,
        action: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> OrganizationAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            OrganizationAuditEntry(
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_recent(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[OrganizationAuditEntry]:
        """The *limit* most recent audit entries for *organization_id*."""
        return await self._audit.list_recent_for_org(organization_id, limit=limit)


__all__ = ["OrganizationAuditService"]
