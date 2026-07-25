"""Project membership management.

Per docs/034 "PROJECT MEMBERS": Invite Member, Remove Member, Transfer
Ownership, Assign Roles, Deactivate Member, Reactivate Member, Track
Membership History.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import ProjectActivityType, ProjectMemberStatus
from app.models.project_member import ProjectMember
from app.models.project_role import ADMINISTRATOR_ROLE_ID, OWNER_ROLE_ID
from app.repositories.project_member import ProjectMemberRepository
from app.services.activity import ProjectActivityService


class ProjectMemberService:
    """Adds, reads, updates, and removes project memberships."""

    def __init__(self, members: ProjectMemberRepository, activity: ProjectActivityService) -> None:
        self._members = members
        self._activity = activity

    async def add(
        self,
        project_id: UUID,
        user_id: UUID,
        *,
        organization_id: UUID,
        role_id: UUID,
        invited_by: UUID | None = None,
    ) -> ProjectMember:
        """Add *user_id* to *project_id* directly, with *role_id* ("Invite Member")."""
        member = await self._members.create(
            ProjectMember(
                project_id=project_id,
                organization_id=organization_id,
                user_id=user_id,
                role_id=role_id,
                invited_by=invited_by,
            )
        )
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            actor_id=invited_by,
            activity_type=ProjectActivityType.MEMBER_ADDED,
        )
        return member

    async def get(self, project_id: UUID, user_id: UUID) -> ProjectMember:
        """Return *user_id*'s membership in *project_id*.

        Raises:
            NotFoundError: If *user_id* is not a member of *project_id*.
        """
        member = await self._members.get(project_id, user_id)
        if member is None:
            raise NotFoundError(f"User '{user_id}' is not a member of this project.")
        return member

    async def list_for_project(self, project_id: UUID) -> list[ProjectMember]:
        """Every member of *project_id* ("Track Membership History")."""
        return await self._members.list_for_project(project_id)

    async def project_ids_for_user(self, user_id: UUID) -> set[UUID]:
        """Every project id *user_id* is a member of ("Prevent cross-project access")."""
        return {m.project_id for m in await self._members.list_for_user(user_id)}

    async def is_member(self, project_id: UUID, user_id: UUID) -> bool:
        """Whether *user_id* is a member of *project_id*."""
        return await self._members.get(project_id, user_id) is not None

    async def update_role(
        self, project_id: UUID, user_id: UUID, *, role_id: UUID, organization_id: UUID
    ) -> ProjectMember:
        """Change *user_id*'s role in *project_id* ("Assign Roles").

        Raises:
            BusinessRuleError: If assigning the Owner role this way --
                ownership can only change via :meth:`transfer_ownership`.
        """
        if role_id == OWNER_ROLE_ID:
            raise BusinessRuleError(
                "The Owner role cannot be assigned directly; use ownership transfer instead."
            )
        member = await self.get(project_id, user_id)
        member.role_id = role_id
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            activity_type=ProjectActivityType.ROLE_CHANGED,
        )
        return member

    async def set_status(
        self, project_id: UUID, user_id: UUID, *, status: ProjectMemberStatus
    ) -> ProjectMember:
        """Deactivate or reactivate *user_id*'s membership ("Deactivate
        Member"/"Reactivate Member").
        """
        member = await self.get(project_id, user_id)
        member.status = status
        return member

    async def remove(self, project_id: UUID, user_id: UUID, *, organization_id: UUID) -> None:
        """Remove *user_id* from *project_id* ("Remove Member")."""
        member = await self.get(project_id, user_id)
        await self._members.delete(member.id)
        await self._activity.record(
            project_id,
            organization_id=organization_id,
            activity_type=ProjectActivityType.MEMBER_REMOVED,
        )

    async def transfer_ownership(
        self, project_id: UUID, *, current_owner_id: UUID, new_owner_id: UUID, organization_id: UUID
    ) -> ProjectMember:
        """Transfer project ownership from *current_owner_id* to *new_owner_id*
        ("Transfer Ownership") -- the new owner's membership is promoted to
        the Owner role; the previous owner keeps membership, demoted to
        Administrator.

        Raises:
            NotFoundError: If *new_owner_id* is not already a member of
                *project_id*.
        """
        new_owner_member = await self.get(project_id, new_owner_id)
        new_owner_member.role_id = OWNER_ROLE_ID

        try:
            previous_owner_member = await self.get(project_id, current_owner_id)
            previous_owner_member.role_id = ADMINISTRATOR_ROLE_ID
        except NotFoundError:
            pass

        await self._activity.record(
            project_id,
            organization_id=organization_id,
            activity_type=ProjectActivityType.OWNERSHIP_TRANSFERRED,
        )
        return new_owner_member


__all__ = ["ProjectMemberService"]
