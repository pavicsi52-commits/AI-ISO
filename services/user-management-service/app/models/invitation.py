"""``user_invitations`` table.

Per docs/031 "INVITATIONS": Invite User, Resend Invitation, Accept
Invitation, Reject Invitation, Invitation Expiration, Invitation
Audit, Invitation Tokens, Bulk Invitations. Only the token's hash is
persisted (the raw token is emailed once), mirroring
``services/authentication-service``'s email-verification/password-reset
token pattern.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import InvitationStatus


class UserInvitation(BaseModel):
    """One invitation extended to an (as yet unregistered) email address."""

    __tablename__ = "user_invitations"

    email: Mapped[str] = mapped_column(String(320), index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[InvitationStatus] = mapped_column(
        String(32), default=InvitationStatus.PENDING, index=True
    )
    message: Mapped[str | None] = mapped_column(String(2048), default=None)
    resend_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["UserInvitation"]
