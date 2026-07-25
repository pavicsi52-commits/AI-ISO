"""``project_members`` table -- who belongs to a project, and with which
:class:`~app.models.project_role.ProjectRole`.

``user_id`` is a bare UUID with no foreign key -- this service never
calls out to ``services/authentication-service``/``services
/user-management-service`` for identity, the same cross-service-safe
convention every prior AI-IOS service established.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProjectMemberStatus


class ProjectMember(BaseModel):
    """One user's membership in a project."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_roles.id"))
    status: Mapped[ProjectMemberStatus] = mapped_column(
        String(16), default=ProjectMemberStatus.ACTIVE
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["ProjectMember"]
