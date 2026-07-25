"""``organization_roles`` table -- organization-scoped role assignments.

Per docs/032 "ROLE TYPES"/"ORGANIZATION ROLES". The assignment's scope
*is* its inherited ``organization_id`` column (per
:class:`shared_core.base.tenant_mixin.TenantMixin`) -- no separate
duplicate column is needed for "which organization does this grant
apply to."
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssignmentStatus


class OrganizationRole(BaseModel):
    """One organization-scoped role grant to one user."""

    __tablename__ = "organization_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "organization_id", name="uq_organization_role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    status: Mapped[AssignmentStatus] = mapped_column(String(16), default=AssignmentStatus.ACTIVE)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["OrganizationRole"]
