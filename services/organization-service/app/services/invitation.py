"""Organization invitations.

Per docs/033 "ORGANIZATION INVITATIONS": Invite Member, Accept, Reject,
Resend, Expire, Audit, Bulk Invitations. Only the token's hash is
persisted (the raw token is emailed once), the exact same pattern
``services/user-management-service``'s own invitation flow established.
Accepting an invitation creates a real
:class:`~app.models.member.OrganizationMember` row -- this service
never calls out to ``services/authentication-service`` to provision
login credentials, the identical scope boundary
``services/user-management-service``'s own ``InvitationService``
documents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.conflict import ConflictError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.apikey import generate_random_token

from app.models.enums import InvitationStatus, MemberRole, OrganizationActivityType
from app.models.invitation import OrganizationInvitation
from app.models.member import OrganizationMember
from app.notifications.organization_notifications import OrganizationNotificationService
from app.repositories.invitation import OrganizationInvitationRepository
from app.repositories.member import OrganizationMemberRepository
from app.services.activity import OrganizationActivityService
from app.services.quota import OrganizationQuotaService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_INVITATION_TTL_DAYS = 7


class InvitationService:
    """Invites, resends, accepts, and rejects organization invitations."""

    def __init__(
        self,
        invitations: OrganizationInvitationRepository,
        members: OrganizationMemberRepository,
        activity: OrganizationActivityService,
        notifications: OrganizationNotificationService,
        quotas: OrganizationQuotaService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._invitations = invitations
        self._members = members
        self._activity = activity
        self._notifications = notifications
        self._quotas = quotas
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def invite(
        self,
        organization_id: UUID,
        *,
        email: str,
        invited_by: UUID,
        role: MemberRole,
        department_id: UUID | None,
        team_id: UUID | None,
        message: str | None,
        invite_base_url: str,
    ) -> tuple[OrganizationInvitation, str]:
        """Invite *email* to *organization_id*, returning ``(record, raw_token)``
        ("Invite Member").

        Raises:
            ConflictError: If *email* already has a pending invitation to this org.
        """
        existing = await self._invitations.get_pending_for_email(organization_id, email)
        if existing is not None:
            raise ConflictError(f"Email {email!r} already has a pending invitation.")

        raw_token = generate_random_token()
        record = await self._invitations.create(
            OrganizationInvitation(
                organization_id=organization_id,
                email=email,
                invited_by=invited_by,
                token_hash=sha256_hex(raw_token),
                role=role,
                department_id=department_id,
                team_id=team_id,
                message=message,
                expires_at=datetime.now(UTC) + timedelta(days=_INVITATION_TTL_DAYS),
            )
        )
        await self._notifications.send_invitation(
            email, invite_url=f"{invite_base_url}?token={raw_token}", message=message
        )
        await self._activity.record(
            organization_id,
            actor_id=invited_by,
            activity_type=OrganizationActivityType.MEMBER_INVITED,
        )
        return record, raw_token

    async def resend(self, organization_id: UUID, email: str, *, invite_base_url: str) -> str:
        """Resend the invitation for *email*, returning a fresh raw token ("Resend").

        Raises:
            AuthenticationError: If *email* has no pending invitation.
        """
        record = await self._invitations.get_pending_for_email(organization_id, email)
        if record is None:
            raise AuthenticationError("No pending invitation for this email.")
        raw_token = generate_random_token()
        record.token_hash = sha256_hex(raw_token)
        record.resend_count += 1
        record.expires_at = datetime.now(UTC) + timedelta(days=_INVITATION_TTL_DAYS)
        await self._notifications.send_invitation_reminder(
            email, invite_url=f"{invite_base_url}?token={raw_token}"
        )
        return raw_token

    async def accept(self, *, token: str, user_id: UUID) -> OrganizationMember:
        """Accept an invitation, creating a new membership ("Accept").

        Per docs/033 "SECURITY": "Enforce quotas." -- an organization at
        its ``max_users`` limit rejects new acceptances even though the
        invitation itself was already sent; the quota is checked against
        actual membership, not outstanding invitations.

        Raises:
            AuthenticationError: If *token* is invalid, expired, or not pending.
            BusinessRuleError: If accepting would exceed the organization's
                ``max_users`` quota.
        """
        record = await self._resolve_pending(token)
        quota_result = await self._quotas.check_user_quota(record.organization_id)
        if not quota_result.within_quota:
            raise BusinessRuleError(
                f"This organization has reached its user quota "
                f"({quota_result.current}/{quota_result.maximum})."
            )
        member = await self._members.create(
            OrganizationMember(
                organization_id=record.organization_id,
                user_id=user_id,
                role=record.role,
                department_id=record.department_id,
                team_id=record.team_id,
            )
        )
        record.status = InvitationStatus.ACCEPTED
        record.accepted_at = datetime.now(UTC)
        record.accepted_member_id = member.id
        await self._activity.record(
            record.organization_id,
            actor_id=user_id,
            activity_type=OrganizationActivityType.MEMBER_JOINED,
        )
        return member

    async def reject(self, token: str) -> OrganizationInvitation:
        """Reject an invitation ("Reject").

        Raises:
            AuthenticationError: If *token* is invalid, expired, or not pending.
        """
        record = await self._resolve_pending(token)
        record.status = InvitationStatus.REJECTED
        record.rejected_at = datetime.now(UTC)
        return record

    async def _resolve_pending(self, token: str) -> OrganizationInvitation:
        record = await self._invitations.get_by_token_hash(sha256_hex(token))
        if record is None or record.status != InvitationStatus.PENDING:
            raise AuthenticationError("Invitation is invalid or has already been resolved.")
        if record.expires_at <= datetime.now(UTC):
            record.status = InvitationStatus.EXPIRED
            raise AuthenticationError("Invitation has expired.")
        return record


__all__ = ["InvitationService"]
