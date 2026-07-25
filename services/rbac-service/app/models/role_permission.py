"""``role_permissions`` table -- the role/permission grant join.

Per docs/032 REST list: ``POST/DELETE /roles/{id}/permissions{,/{permissionId}}``.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class RolePermission(BaseModel):
    """One permission granted to one role."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE")
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["RolePermission"]
