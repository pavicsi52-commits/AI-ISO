"""User invitations.

Per docs/031 "INVITATIONS": Invite User, Resend Invitation, Accept
Invitation, Reject Invitation, Invitation Expiration, Invitation
Audit, Invitation Tokens, Bulk Invitations. Only the token's hash is
persisted (the raw token is emailed once), mirroring
``services/authentication-service``'s email-verification/password-reset
token pattern -- reuses the exact same
:func:`shared_core.security.apikey.generate_random_token`/
:func:`shared_core.helpers.hash_helper.sha256_hex` primitives.

Accepting an invitation creates a real :class:`~app.models.user.User`
row via :class:`~app.services.user.UserService` -- this service never
calls out to ``services/authentication-service`` to provision login
credentials (no such integration is named anywhere in docs/031, which
explicitly scopes authentication itself out: "This service SHALL NOT
authenticate users"). Whatever wires "this user can now log in" is a
deliberately separate concern, out of scope here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.helpers.hash_helper import sha256_hex
from shared_core.security.apikey import generate_random_token

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.user_events import InvitationAcceptedEvent, UserInvitedEvent
from app.models.enums import ActivityType, InvitationStatus, UserStatus
from app.models.invitation import UserInvitation
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.repositories.invitation import UserInvitationRepository
from app.services.activity import UserActivityService
from app.services.user import UserService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_INVITATION_TTL_DAYS = 7


class InvitationService:
    """Invites, resends, accepts, and rejects user invitations."""

    def __init__(
        self,
        invitations: UserInvitationRepository,
        users: UserService,
        activity: UserActivityService,
        notifications: UserNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._invitations = invitations
        self._users = users
        self._activity = activity
        self._notifications = notifications
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def invite(
        self, email: str, *, invited_by: UUID, message: str | None, invite_base_url: str
    ) -> tuple[UserInvitation, str]:
        """Invite *email*, returning ``(record, raw_token)`` ("Invite User").

        Raises:
            ConflictError: If *email* already has a pending invitation.
        """
        existing = await self._invitations.get_pending_for_email(email)
        if existing is not None:
            raise ConflictError(f"Email {email!r} already has a pending invitation.")

        raw_token = generate_random_token()
        record = await self._invitations.create(
            UserInvitation(
                email=email,
                invited_by=invited_by,
                token_hash=sha256_hex(raw_token),
                message=message,
                expires_at=datetime.now(UTC) + timedelta(days=_INVITATION_TTL_DAYS),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._notifications.send_invitation(
            email, invite_url=f"{invite_base_url}?token={raw_token}", message=message
        )
        await self._activity.record(invited_by, activity_type=ActivityType.INVITATION_SENT)
        await self._publish(
            UserInvitedEvent(source_service="user-management-service", payload={"email": email})
        )
        return record, raw_token

    async def resend(self, email: str, *, invite_base_url: str) -> str:
        """Resend the invitation for *email*, returning a fresh raw token ("Resend Invitation").

        Raises:
            AuthenticationError: If *email* has no pending invitation.
        """
        record = await self._invitations.get_pending_for_email(email)
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

    async def accept(self, *, token: str, username: str, display_name: str | None) -> User:
        """Accept an invitation, creating a new user ("Accept Invitation").

        Raises:
            AuthenticationError: If *token* is invalid, expired, or not pending.
        """
        record = await self._resolve_pending(token)
        user = await self._users.create(
            username=username,
            email=record.email,
            display_name=display_name,
            first_name=None,
            middle_name=None,
            last_name=None,
            phone_number=None,
            timezone="UTC",
            language="en",
            locale="en-US",
            status=UserStatus.ACTIVE,
        )
        record.status = InvitationStatus.ACCEPTED
        record.accepted_at = datetime.now(UTC)
        record.accepted_user_id = user.id
        await self._activity.record(user.id, activity_type=ActivityType.INVITATION_ACCEPTED)
        await self._publish(
            InvitationAcceptedEvent(
                source_service="user-management-service",
                payload={"email": record.email, "user_id": str(user.id)},
            )
        )
        return user

    async def reject(self, token: str) -> UserInvitation:
        """Reject an invitation ("Reject Invitation").

        Raises:
            AuthenticationError: If *token* is invalid, expired, or not pending.
        """
        record = await self._resolve_pending(token)
        record.status = InvitationStatus.REJECTED
        record.rejected_at = datetime.now(UTC)
        return record

    async def _resolve_pending(self, token: str) -> UserInvitation:
        record = await self._invitations.get_by_token_hash(sha256_hex(token))
        if record is None or record.status != InvitationStatus.PENDING:
            raise AuthenticationError("Invitation is invalid or has already been resolved.")
        if record.expires_at <= datetime.now(UTC):
            record.status = InvitationStatus.EXPIRED
            raise AuthenticationError("Invitation has expired.")
        return record


__all__ = ["InvitationService"]
