"""Project audit trail.

Per docs/034 "AUDIT": Project Creation, Updates, Deletion, Membership
Changes, Role Changes, Ownership Changes, Settings Updates, Template
Usage, Resource Linking, Administrative Operations. Records
specifically *privileged* actions with a before/after snapshot, the
same distinction ``app/services/activity.py``'s narrative feed doesn't
attempt -- mirrors ``services/organization-service``'s identical
``OrganizationAuditService`` shape. See ``app/services/activity.py``'s
own docstring for why ``organization_id`` must be passed explicitly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.project_audit import ProjectAuditEntry
from app.repositories.project_audit import ProjectAuditRepository


class ProjectAuditService:
    """Records and lists privileged-action audit entries for a project."""

    def __init__(self, audit: ProjectAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> ProjectAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            ProjectAuditEntry(
                project_id=project_id,
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

    async def list_recent(self, project_id: UUID, *, limit: int = 50) -> list[ProjectAuditEntry]:
        """The *limit* most recent audit entries for *project_id*."""
        return await self._audit.list_recent_for_project(project_id, limit=limit)


__all__ = ["ProjectAuditService"]
