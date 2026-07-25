"""Organization activity tracking.

Per docs/033's own 19-table list: ``organization_activity`` is this
service's narrative "what happened and why" feed -- see
``app/models/activity.py``'s docstring for how it differs from
``organization_audit``. Every other service in this codebase that
tracks its own activity (``services/user-management-service``'s
``UserActivityService``, ``services/rbac-service``'s audit trail)
follows this exact same recorder shape.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.activity import OrganizationActivityEntry
from app.models.enums import OrganizationActivityType
from app.repositories.activity import OrganizationActivityRepository


class OrganizationActivityService:
    """Records and lists organization-activity feed entries."""

    def __init__(self, activity: OrganizationActivityRepository) -> None:
        self._activity = activity

    async def record(
        self,
        organization_id: UUID,
        *,
        activity_type: OrganizationActivityType,
        actor_id: UUID | None = None,
        description: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> OrganizationActivityEntry:
        """Record one activity event ("Track ...")."""
        return await self._activity.create(
            OrganizationActivityEntry(
                organization_id=organization_id,
                actor_id=actor_id,
                activity_type=activity_type,
                description=description,
                detail=detail or {},
            )
        )

    async def list_recent(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[OrganizationActivityEntry]:
        """The *limit* most recent activity entries for *organization_id*."""
        return await self._activity.list_recent_for_org(organization_id, limit=limit)


__all__ = ["OrganizationActivityService"]
