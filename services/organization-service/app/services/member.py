"""Organization membership management.

Per docs/033's own 19-table list: no separate REST surface is named for
``organization_members`` -- membership rows are created either directly
(:meth:`OrganizationMemberService.add`, used by ``POST /organizations``
to make its creator the owner) or by
:class:`~app.services.invitation.InvitationService.accept`.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import MemberRole, OrganizationActivityType
from app.models.member import OrganizationMember
from app.repositories.member import OrganizationMemberRepository
from app.services.activity import OrganizationActivityService


class OrganizationMemberService:
    """Adds, reads, and removes organization memberships."""

    def __init__(
        self, members: OrganizationMemberRepository, activity: OrganizationActivityService
    ) -> None:
        self._members = members
        self._activity = activity

    async def add(
        self, organization_id: UUID, user_id: UUID, *, role: MemberRole
    ) -> OrganizationMember:
        """Add *user_id* to *organization_id* directly, with *role*."""
        return await self._members.create(
            OrganizationMember(organization_id=organization_id, user_id=user_id, role=role)
        )

    async def get(self, organization_id: UUID, user_id: UUID) -> OrganizationMember:
        """Return *user_id*'s membership in *organization_id*.

        Raises:
            NotFoundError: If *user_id* is not a member of *organization_id*.
        """
        member = await self._members.get(organization_id, user_id)
        if member is None:
            raise NotFoundError(f"User '{user_id}' is not a member of this organization.")
        return member

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationMember]:
        """Every member of *organization_id*."""
        return await self._members.list_for_org(organization_id)

    async def remove(self, organization_id: UUID, user_id: UUID) -> None:
        """Remove *user_id* from *organization_id*."""
        member = await self.get(organization_id, user_id)
        await self._members.delete(member.id)
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.MEMBER_REMOVED
        )


__all__ = ["OrganizationMemberService"]
