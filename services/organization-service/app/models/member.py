"""``organization_members`` table -- who belongs to an organization.

Per docs/033's own 19-table list: no separate "department_members" or
"team_members" join table is named, so each member's department/
business-unit/team assignment lives directly on this one row
(nullable -- a member need not be assigned to any of them yet), rather
than three parallel many-to-many tables docs/033 never names.
``user_id`` is a bare UUID with no foreign key -- this service never
calls out to ``services/authentication-service``/``services
/user-management-service`` for identity, the same cross-service-safe
convention every prior AI-IOS service established.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MemberRole, MemberStatus


class OrganizationMember(BaseModel):
    """One user's membership in an organization."""

    __tablename__ = "organization_members"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role: Mapped[MemberRole] = mapped_column(String(16), default=MemberRole.MEMBER)
    status: Mapped[MemberStatus] = mapped_column(String(16), default=MemberStatus.ACTIVE)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_departments.id", ondelete="SET NULL"), default=None
    )
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_business_units.id", ondelete="SET NULL"), default=None
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organization_teams.id", ondelete="SET NULL"), default=None
    )


__all__ = ["OrganizationMember"]
