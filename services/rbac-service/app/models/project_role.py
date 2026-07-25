"""``project_roles`` table -- project-scoped role assignments.

Per docs/032 "ROLE TYPES"/"PROJECT ROLES". The assignment's scope is
its inherited ``organization_id`` *and* ``project_id`` columns -- see
:mod:`app.models.organization_role`'s docstring for why no separate
scope column is added.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssignmentStatus


class ProjectRole(BaseModel):
    """One project-scoped role grant to one user."""

    __tablename__ = "project_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "project_id", name="uq_project_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    status: Mapped[AssignmentStatus] = mapped_column(String(16), default=AssignmentStatus.ACTIVE)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ProjectRole"]
