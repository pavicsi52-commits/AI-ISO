"""``permissions`` table.

Per docs/032 "PERMISSION MODEL": Permission ID, Name, Code,
Description, Category, Resource, Action, Scope, Status, Version,
Metadata -- every field named there, verbatim.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.security.rbac import PermissionScope
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionAction, PermissionStatus, ResourceType


class Permission(BaseModel):
    """One fine-grained permission: a resource/action pair plus scope."""

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    category: Mapped[str | None] = mapped_column(String(64), default=None)
    resource: Mapped[ResourceType] = mapped_column(String(32), index=True)
    action: Mapped[PermissionAction] = mapped_column(String(32), index=True)
    scope: Mapped[PermissionScope] = mapped_column(String(16), default=PermissionScope.GLOBAL)
    status: Mapped[PermissionStatus] = mapped_column(String(16), default=PermissionStatus.ACTIVE)
    version: Mapped[int] = mapped_column(default=1)
    permission_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("permission_groups.id", ondelete="SET NULL"), default=None
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Permission"]
