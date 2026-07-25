"""User activity tracking.

Per docs/031 "USER ACTIVITY": Profile Updates, Status Changes,
Preference Changes, Invitation Events, Import, Export, Last Active,
Login History Reference. Doubles as this service's "AUDIT" trail for
those same operations -- docs/031 lists a single ``user_activity``
table (not a separate audit table the way
``services/authentication-service`` has both ``login_history`` and
``authentication_audit``), so every other service here calls through
this one recorder rather than a parallel audit mechanism. Routine
column-level Create/Update/Delete auditing for every table is already
automatic via :mod:`shared_core.database.audit`, wired into
``BaseRepository`` itself -- this covers the *narrative*, "what
happened and why" layer on top.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.activity import UserActivityEntry
from app.models.enums import ActivityType
from app.repositories.activity import UserActivityRepository


class UserActivityService:
    """Records and lists user-activity feed entries."""

    def __init__(self, activity: UserActivityRepository) -> None:
        self._activity = activity

    async def record(
        self,
        user_id: UUID,
        *,
        activity_type: ActivityType,
        description: str | None = None,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> UserActivityEntry:
        """Record one activity event ("Track ...")."""
        return await self._activity.create(
            UserActivityEntry(
                user_id=user_id,
                activity_type=activity_type,
                description=description,
                detail=detail or {},
                ip_address=ip_address,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def list_recent(self, user_id: UUID, *, limit: int = 50) -> list[UserActivityEntry]:
        """The *limit* most recent activity entries for *user_id* ("Last Active")."""
        return await self._activity.list_recent_for_user(user_id, limit=limit)


__all__ = ["UserActivityService"]
