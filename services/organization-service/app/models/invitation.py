"""``organization_invitations`` table. Per docs/033 "ORGANIZATION
INVITATIONS": Invite Member, Accept, Reject, Resend, Expire, Audit,
Bulk Invitations. Only the token's hash is persisted (the raw token is
emailed once), the exact same pattern
``services/user-management-service``'s own invitation flow established.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import InvitationStatus, MemberRole


class OrganizationInvitation(BaseModel):
    """One pending, accepted, rejected, or expired invitation to join an organization."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )

    email: Mapped[str] = mapped_column(String(255), index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column()
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    role: Mapped[MemberRole] = mapped_column(String(16), default=MemberRole.MEMBER)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_departments.id", ondelete="SET NULL"), default=None
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_teams.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[InvitationStatus] = mapped_column(String(16), default=InvitationStatus.PENDING)
    message: Mapped[str | None] = mapped_column(String(2048), default=None)
    resend_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_member_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["OrganizationInvitation"]
