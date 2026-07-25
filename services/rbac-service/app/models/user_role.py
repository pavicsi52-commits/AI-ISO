"""``user_roles`` table -- global/system-scoped role assignments.

Per docs/032 REST list: ``POST/DELETE /users/{id}/roles{,/{roleId}}``.
Org/project-*scoped* assignments live in their own
``organization_roles``/``project_roles`` tables instead of a
``scope``/``scope_id`` pair here, so each assignment kind gets its own
straightforward foreign key rather than a polymorphic one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssignmentStatus


class UserRole(BaseModel):
    """One system-wide role grant to one user."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    status: Mapped[AssignmentStatus] = mapped_column(String(16), default=AssignmentStatus.ACTIVE)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["UserRole"]
