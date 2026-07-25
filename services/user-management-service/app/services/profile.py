"""User profile management.

Per docs/031 "USER PROFILE": Personal Information, Contact
Information, Biography, Job Title, Department, Employee ID, Manager,
Profile Photo, Custom Fields. Per "USER ACTIVITY": "Profile Updates"
is a tracked activity type -- caught missing via live HTTP testing
(``GET /users/activity`` stayed empty after a ``PUT /users/profile``)
and fixed by threading :class:`~app.services.activity.UserActivityService`
through, the same way :class:`~app.services.user.UserService` already
records "Status Changes".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ActivityType
from app.models.profile import UserProfile
from app.repositories.profile import UserProfileRepository
from app.services.activity import UserActivityService


class UserProfileService:
    """Creates and updates the extended profile for a user."""

    def __init__(self, profiles: UserProfileRepository, activity: UserActivityService) -> None:
        self._profiles = profiles
        self._activity = activity

    async def get_or_create(self, user_id: UUID) -> UserProfile:
        """Return *user_id*'s profile, creating an empty one if it doesn't exist yet."""
        existing = await self._profiles.get_for_user(user_id)
        if existing is not None:
            return existing
        return await self._profiles.create(
            UserProfile(user_id=user_id, organization_id=DEFAULT_ORGANIZATION_ID)
        )

    async def update(
        self,
        user_id: UUID,
        *,
        biography: str | None,
        job_title: str | None,
        department: str | None,
        employee_id: str | None,
        manager_id: UUID | None,
        custom_fields: dict[str, Any],
    ) -> UserProfile:
        """Update *user_id*'s profile, creating it first if necessary ("Profile Updates")."""
        profile = await self.get_or_create(user_id)
        profile.biography = biography
        profile.job_title = job_title
        profile.department = department
        profile.employee_id = employee_id
        profile.manager_id = manager_id
        profile.custom_fields = custom_fields
        await self._activity.record(user_id, activity_type=ActivityType.PROFILE_UPDATED)
        return profile


__all__ = ["UserProfileService"]
