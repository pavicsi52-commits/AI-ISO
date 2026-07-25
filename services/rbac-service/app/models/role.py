"""``roles`` table.

Per docs/032 "ROLE TYPES"/"ROLE HIERARCHY"/"DEFAULT SYSTEM ROLES":
Inheritance, Parent Roles, Child Roles, Permission Aggregation.
``parent_role_id`` is a self-referential FK -- ``role_type`` and
``is_system`` distinguish the 10 seeded default roles from everything
an administrator creates later, per :mod:`app.services.hierarchy`'s
cycle-detection guard.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RoleStatus, RoleType


class Role(BaseModel):
    """One role -- a named, hierarchical bundle of permissions."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    role_type: Mapped[RoleType] = mapped_column(String(32), default=RoleType.CUSTOM, index=True)
    status: Mapped[RoleStatus] = mapped_column(String(16), default=RoleStatus.ACTIVE)
    parent_role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), default=None
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Role"]
